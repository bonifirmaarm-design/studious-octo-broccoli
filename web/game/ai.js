// The opponent. Not a solver -- it reacts to pressure, defends its weaker
// lane and saves elixir for a push, which is enough to make a real match.

import { RIVER, FIELD } from './config.js';

const LANES = [-4.2, 4.0];

export class Bot {
  constructor(battle, deck, team = 'red', difficulty = 1.0) {
    this.battle = battle;
    this.team = team;
    this.deck = deck;
    this.difficulty = difficulty;
    this.hand = deck.slice(0, 4);
    this.queue = deck.slice(4);
    this.think = 1.5;
  }

  cycle(card) {
    const i = this.hand.indexOf(card);
    this.queue.push(card);
    this.hand[i] = this.queue.shift();
  }

  /** Enemy units on our half or approaching it, grouped by lane. */
  threat() {
    const foes = this.battle.units.filter(u => !u.dead && u.team !== this.team);
    const lanes = LANES.map(z => ({
      z,
      pressure: 0,
      lead: null,
    }));
    for (const foe of foes) {
      const lane = foe.z < 0 ? lanes[0] : lanes[1];
      const advance = this.team === 'red' ? foe.x : -foe.x;
      if (advance < -2) continue;                       // still deep in their half
      lane.pressure += foe.maxHp / 400 + 1;
      if (!lane.lead || (this.team === 'red' ? foe.x > lane.lead.x : foe.x < lane.lead.x)) {
        lane.lead = foe;
      }
    }
    return lanes;
  }

  update(dt) {
    if (this.battle.over) return;
    this.think -= dt;
    if (this.think > 0) return;
    this.think = 0.6 + Math.random() * 0.9 / this.difficulty;

    const elixir = this.battle.elixir[this.team];
    const lanes = this.threat();
    const pressed = lanes.filter(l => l.pressure > 0).sort((a, b) => b.pressure - a.pressure)[0];

    if (pressed && pressed.pressure >= 1) {
      // Defend: answer in the threatened lane, just behind our own line.
      const card = this.pickDefence(pressed, elixir);
      if (card) {
        const x = this.homeX(3.2 + Math.random() * 1.6);
        const z = pressed.lead ? pressed.lead.z * 0.85 : pressed.z;
        if (this.battle.play(this.team, card, x, z)) { this.cycle(card); return; }
      }
      return;
    }

    // Attack: build up, then commit. Bigger pushes need more banked elixir.
    const wantBank = 7 + (1 - this.difficulty) * 2;
    if (elixir < wantBank) return;

    const affordable = this.hand.filter(c => c.cost <= elixir)
      .sort((a, b) => b.cost - a.cost);
    const card = affordable[0];
    if (!card) return;
    const z = LANES[Math.random() < 0.5 ? 0 : 1];
    const x = this.homeX(1.5 + Math.random() * 1.5);
    if (this.battle.play(this.team, card, x, z)) this.cycle(card);
  }

  pickDefence(lane, elixir) {
    const airborne = lane.lead && lane.lead.flying;
    const options = this.hand.filter(c => c.cost <= elixir);
    if (!options.length) return null;
    const scored = options.map(card => {
      let score = card.cost;                              // cheap answers first
      const spec = CARD_SPECS[card.unit];
      if (airborne && spec && spec.targets === 'ground') score += 100;
      if (spec && spec.targets === 'buildings') score += 60;   // not a defender
      return { card, score };
    }).sort((a, b) => a.score - b.score);
    return scored[0].card;
  }

  /** X coordinate `back` metres behind our side of the river. */
  homeX(back) {
    const x = this.team === 'red' ? RIVER.xMax + back : RIVER.xMin - back;
    return Math.min(FIELD.xMax - 1.5, Math.max(FIELD.xMin + 1.5, x));
  }
}

// Filled in by main.js so the bot can reason about what a card summons
// without importing the whole unit table into its own scope.
export const CARD_SPECS = {};
