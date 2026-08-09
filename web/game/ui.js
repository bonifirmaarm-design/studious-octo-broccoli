// HUD: elixir, the hand of cards, crowns, clock, chest and the result screen.

import { CARDS, MATCH, RARITY_COLORS } from './config.js';

export class HUD {
  constructor(root, { onSelect, onChest }) {
    this.root = root;
    this.onSelect = onSelect;
    this.onChest = onChest;
    this.selected = null;
    this.cardNodes = new Map();
    this.build();
  }

  build() {
    this.root.innerHTML = `
      <div id="topbar">
        <div class="crowns" id="crowns-blue"><span class="tag blue">СИНИЙ</span><b>0</b></div>
        <div id="clock">3:00</div>
        <div class="crowns" id="crowns-red"><b>0</b><span class="tag red">КРАСНЫЙ</span></div>
      </div>
      <div id="bottombar">
        <div id="nextcard">
          <div class="label">Далее</div>
          <div class="mini" id="next-mini"></div>
          <button id="chest" title="Сундук: выдаёт легендарную карту">🎁 Сундук</button>
        </div>
        <div id="hand"></div>
        <div id="elixir">
          <div id="elixir-fill"></div>
          <div id="elixir-pips"></div>
          <span id="elixir-value">5</span>
        </div>
      </div>
      <div id="result" hidden><div class="panel"><h2></h2><p></p>
        <button id="again">Ещё раз</button></div></div>
    `;
    this.hand = this.root.querySelector('#hand');
    this.elixirFill = this.root.querySelector('#elixir-fill');
    this.elixirValue = this.root.querySelector('#elixir-value');
    this.clock = this.root.querySelector('#clock');
    this.nextMini = this.root.querySelector('#next-mini');
    this.result = this.root.querySelector('#result');

    const pips = this.root.querySelector('#elixir-pips');
    for (let i = 0; i < MATCH.elixirMax; i++) pips.appendChild(document.createElement('i'));

    this.root.querySelector('#chest').onclick = () => this.onChest();
    this.root.querySelector('#again').onclick = () => location.reload();
  }

  cardNode(card) {
    const node = document.createElement('button');
    node.className = 'card';
    node.style.setProperty('--rarity', RARITY_COLORS[card.rarity] || '#9fb4d8');
    node.innerHTML = `
      <img alt="" src="./assets/cards/${card.art}.png" loading="lazy">
      <span class="cost">${card.cost}</span>
      <span class="name">${card.name}</span>`;
    node.onclick = () => this.select(card);
    return node;
  }

  setHand(hand, next) {
    this.hand.innerHTML = '';
    this.cardNodes.clear();
    for (const card of hand) {
      const node = this.cardNode(card);
      this.cardNodes.set(card.id, node);
      this.hand.appendChild(node);
    }
    this.nextMini.innerHTML = next
      ? `<img alt="" src="./assets/cards/${next.art}.png"><span>${next.cost}</span>` : '';
    if (this.selected && !hand.includes(this.selected)) this.selected = null;
    this.refreshSelection();
  }

  select(card) {
    this.selected = this.selected === card ? null : card;
    this.refreshSelection();
    this.onSelect(this.selected);
  }

  refreshSelection() {
    for (const [id, node] of this.cardNodes) {
      node.classList.toggle('selected', !!this.selected && this.selected.id === id);
    }
  }

  update(battle, team = 'blue') {
    const elixir = battle.elixir[team];
    this.elixirFill.style.width = `${(elixir / MATCH.elixirMax) * 100}%`;
    this.elixirValue.textContent = Math.floor(elixir);
    for (const [id, node] of this.cardNodes) {
      const card = CARDS.find(c => c.id === id);
      node.classList.toggle('poor', card.cost > elixir);
    }

    const left = Math.max(0, (battle.time < MATCH.duration ? MATCH.duration
      : MATCH.duration + MATCH.overtime) - battle.time);
    const minutes = Math.floor(left / 60);
    const seconds = Math.floor(left % 60).toString().padStart(2, '0');
    this.clock.textContent = `${minutes}:${seconds}`;
    this.clock.classList.toggle('overtime', battle.time >= MATCH.duration);

    this.root.querySelector('#crowns-blue b').textContent = battle.crowns.blue;
    this.root.querySelector('#crowns-red b').textContent = battle.crowns.red;
  }

  showResult(winner, reason) {
    const titles = { blue: 'Победа!', red: 'Поражение', null: 'Ничья' };
    this.result.hidden = false;
    this.result.querySelector('h2').textContent = titles[winner] ?? 'Ничья';
    this.result.querySelector('h2').className = winner === 'blue' ? 'win' : 'lose';
    this.result.querySelector('p').textContent = reason;
  }

  toast(text) {
    const node = document.createElement('div');
    node.className = 'toast';
    node.textContent = text;
    this.root.appendChild(node);
    setTimeout(() => node.remove(), 2600);
  }
}
