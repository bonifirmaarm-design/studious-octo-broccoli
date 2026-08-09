// Wiring: scene, loading, input, the tick loop.

import * as THREE from 'three';
import { Battle, findCard } from './battle.js';
import { Bot, CARD_SPECS } from './ai.js';
import { CameraRig, VIEWS } from './camera.js';
import { CARDS, FIELD, KING_MODELS, TOWER_ARCHERS, UNITS, canDeploy } from './config.js';
import { HUD } from './ui.js';
import { View } from './view.js';

for (const card of CARDS) CARD_SPECS[card.unit] = UNITS[card.unit];

// --- renderer -------------------------------------------------------------

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.getElementById('stage').appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1120);
scene.fog = new THREE.Fog(0x0d1120, 70, 210);

const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 0.1, 800);
const rig = new CameraRig(camera, renderer.domElement);

scene.add(new THREE.HemisphereLight(0xc3d8ff, 0x2a2f3e, 1.45));
const sun = new THREE.DirectionalLight(0xfff1d6, 2.5);
sun.position.set(24, 42, 18);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 6;
sun.shadow.camera.far = 140;
Object.assign(sun.shadow.camera, { left: -28, right: 28, top: 26, bottom: -26 });
sun.shadow.bias = -0.0012;
sun.target.position.set(FIELD.xMid, FIELD.y, 0);
scene.add(sun, sun.target);
const rim = new THREE.DirectionalLight(0x8ab8ff, 0.7);
rim.position.set(-22, 16, -26);
scene.add(rim);

// --- deploy marker --------------------------------------------------------

const marker = new THREE.Mesh(
  new THREE.RingGeometry(0.75, 1.05, 48),
  new THREE.MeshBasicMaterial({ color: 0x8fe8ff, transparent: true, opacity: 0.9,
                                side: THREE.DoubleSide, depthWrite: false }));
marker.rotation.x = -Math.PI / 2;
marker.visible = false;
scene.add(marker);

const deployZone = new THREE.Mesh(
  new THREE.PlaneGeometry(1, 1),
  new THREE.MeshBasicMaterial({ color: 0x4a86ff, transparent: true, opacity: 0.10,
                                depthWrite: false }));
deployZone.rotation.x = -Math.PI / 2;
deployZone.visible = false;
scene.add(deployZone);

// --- load -----------------------------------------------------------------

const view = new View(scene);
const status = document.getElementById('loading');
const bar = document.getElementById('loadbar');

// Every model the match can show: card units, the kings on the king towers
// and the archers standing on the princess towers.
const modelKeys = [...new Set([
  ...CARDS.flatMap(c => Object.values(UNITS[c.unit].model)),
  ...Object.values(KING_MODELS),
  ...Object.values(TOWER_ARCHERS),
])];

status.textContent = 'Загрузка арены…';
await view.loadArena('./assets/arena.glb');
await view.loadUnits(modelKeys, (done, total, key) => {
  status.textContent = `Модели: ${done}/${total} — ${key}`;
  bar.style.width = `${(done / total) * 100}%`;
});

// --- match ----------------------------------------------------------------

const playable = CARDS.filter(c => !c.chestOnly);
const shuffled = [...playable].sort(() => Math.random() - 0.5);

let hand = shuffled.slice(0, 4);
let queue = shuffled.slice(4);

const battle = new Battle(playable, {
  onEvent: event => {
    if (event.type === 'towerDown') {
      hud.toast(event.tower.team === 'red' ? 'Башня противника разрушена!' : 'Наша башня пала!');
    }
    if (event.type === 'kingWoke') {
      hud.toast(event.tower.team === 'red' ? 'Королевская башня врага проснулась'
                                           : 'Наша королевская башня проснулась');
    }
    if (event.type === 'over') hud.showResult(event.winner, event.reason);
  },
});
view.buildTowers(battle.towers);

const bot = new Bot(battle, [...playable].sort(() => Math.random() - 0.5), 'red', 1.0);

let chestUsed = false;
const hud = new HUD(document.getElementById('hud'), {
  onSelect: card => {
    selected = card;
    deployZone.visible = !!card;
  },
  onChest: () => {
    if (chestUsed) { hud.toast('Сундук уже открыт в этом бою'); return; }
    chestUsed = true;
    const trump = findCard('trump');
    queue.unshift(trump);
    hud.toast('Из сундука выпал Мега-Найт Трамп — 10 эликсира!');
    hud.setHand(hand, queue[0]);
  },
});
hud.setHand(hand, queue[0]);

let selected = null;

// The deploy zone covers our half of the field, minus the river.
{
  const width = (FIELD.xMid - 1.05) - FIELD.xMin;
  deployZone.scale.set(width, FIELD.zMax - FIELD.zMin, 1);
  deployZone.position.set(FIELD.xMin + width / 2, FIELD.y + 0.04, 0);
}

// --- pointer --------------------------------------------------------------

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -FIELD.y);

function groundAt(event) {
  pointer.x = (event.clientX / innerWidth) * 2 - 1;
  pointer.y = -(event.clientY / innerHeight) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const point = new THREE.Vector3();
  return raycaster.ray.intersectPlane(groundPlane, point) ? point : null;
}

renderer.domElement.addEventListener('pointermove', event => {
  if (!selected) { marker.visible = false; return; }
  const point = groundAt(event);
  if (!point) { marker.visible = false; return; }
  marker.position.set(point.x, FIELD.y + 0.05, point.z);
  marker.visible = true;
  const ok = battle.canPlay('blue', selected, point.x, point.z);
  marker.material.color.set(ok ? 0x8fe8ff : 0xff6a6a);
});

renderer.domElement.addEventListener('pointerdown', event => {
  if (event.button !== 0 || !selected) return;
  const point = groundAt(event);
  if (!point) return;
  if (!battle.play('blue', selected, point.x, point.z)) {
    if (battle.elixir.blue < selected.cost) hud.toast('Не хватает эликсира');
    else if (!canDeploy('blue', point.x, point.z, battle.towers)) {
      hud.toast('Сюда ставить нельзя — вода или чужая половина');
    }
    return;
  }
  const index = hand.indexOf(selected);
  queue.push(selected);
  hand[index] = queue.shift();
  selected = null;
  marker.visible = false;
  deployZone.visible = false;
  hud.setHand(hand, queue[0]);
});

// --- camera buttons -------------------------------------------------------

for (const name of Object.keys(VIEWS)) {
  const button = document.querySelector(`[data-view="${name}"]`);
  if (button) button.onclick = () => { rig.toggleFree(false); rig.setView(name); syncFlyButton(); };
}
const flyButton = document.getElementById('fly');
flyButton.onclick = () => { rig.toggleFree(); syncFlyButton(); };
function syncFlyButton() {
  flyButton.classList.toggle('on', rig.free);
  flyButton.textContent = rig.free ? '🕹 Полёт: вкл (F)' : '🕹 Полёт: выкл (F)';
  document.getElementById('flyhint').hidden = !rig.free;
}
addEventListener('keyup', e => { if (e.code === 'KeyF') syncFlyButton(); });
syncFlyButton();

// --- loop -----------------------------------------------------------------

document.getElementById('boot').remove();

const clock = new THREE.Clock();
let elapsed = 0;
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  elapsed += dt;

  battle.update(dt);
  bot.update(dt);
  rig.update(dt);

  view.update(dt, elapsed);
  view.now = elapsed;
  view.syncUnits(battle.units, camera, dt);
  view.updateTowers(battle.towers, camera);
  view.syncProjectiles(battle.projectiles);
  view.syncEffects(battle.effects);
  hud.update(battle);

  marker.rotation.z += dt * 1.6;
  renderer.render(scene, camera);
});

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// Exposed for debugging and for the screenshot tool.
window.game = { battle, bot, view, rig, camera, scene, hud, hand, queue, Bot, playable };
