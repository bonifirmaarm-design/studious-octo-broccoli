// Arena geometry and card data.
//
// The world coordinates come from the arena model itself: the playing surface
// is a flat plane at y = 2.33 spanning x -15.7..17.8 and z -7.1..6.8, with the
// river running along z at the field's mid-line and two bridges across it.
// Lanes run along x: blue defends -x, red defends +x.

// Bumped whenever the models are rebuilt. It is appended to every asset URL
// so a browser that cached the previous 24 MB arena cannot serve it back.
export const ASSET_VERSION = '7';

export const FIELD = {
  y: 2.33,
  xMin: -15.7, xMax: 17.8,
  zMin: -7.0, zMax: 6.8,
};
FIELD.xMid = (FIELD.xMin + FIELD.xMax) / 2;
FIELD.zMid = (FIELD.zMin + FIELD.zMax) / 2;

export const RIVER = { xMin: FIELD.xMid - 1.05, xMax: FIELD.xMid + 1.05 };

// Bridges and towers are measured off the arena mesh, not guessed: the decks
// span z -6.45..-4.54 and 4.16..6.07 and their walkway sits 0.3 m above the
// grass, which is why units used to wade through them knee-deep.
export const BRIDGES = [
  { z: -5.50, halfWidth: 0.95 },
  { z: 5.12, halfWidth: 0.95 },
];
export const BRIDGE_Y = 2.63;

// Towers. `lane` is which bridge a unit heading for it will use.
export const TOWERS = [
  { id: 'blue-king', team: 'blue', kind: 'king', x: -13.6, z: 0.15, hp: 4000, range: 7.0, damage: 130, hitEvery: 1.0 },
  { id: 'blue-left', team: 'blue', kind: 'crown', x: -9.15, z: -5.30, hp: 2400, range: 7.5, damage: 95, hitEvery: 0.8 },
  { id: 'blue-right', team: 'blue', kind: 'crown', x: -9.15, z: 5.25, hp: 2400, range: 7.5, damage: 95, hitEvery: 0.8 },
  { id: 'red-king', team: 'red', kind: 'king', x: 15.7, z: 0.15, hp: 4000, range: 7.0, damage: 130, hitEvery: 1.0 },
  { id: 'red-left', team: 'red', kind: 'crown', x: 11.2, z: -5.30, hp: 2400, range: 7.5, damage: 95, hitEvery: 0.8 },
  { id: 'red-right', team: 'red', kind: 'crown', x: 11.2, z: 5.20, hp: 2400, range: 7.5, damage: 95, hitEvery: 0.8 },
];

// Troops chip buildings more slowly than they shred each other, so a lone
// push cannot flatten a tower in seconds.
export const BUILDING_DAMAGE_SCALE = 0.55;

export const TOWER_RADIUS = { king: 1.8, crown: 1.35 };

// Which model plays each team's king, and who mans the princess towers.
export const KING_MODELS = { blue: 'king_blue', red: 'king_red' };
export const TOWER_ARCHERS = { blue: 'archer_blue', red: 'archer_red' };

// Height of the floor inside each tower's battlements, measured off the arena
// mesh (king tower 4.73, princess tower 3.75 in world units). The crew stands
// on that floor, not on top of the crenellations.
export const TOWER_CREW = {
  king: { y: 4.83, height: 2.1 },
  crown: { y: 3.75, height: 1.5 },
};

/** Height of the walkable surface, so units stand on the bridge, not in it. */
export function groundHeight(x, z) {
  const bridge = BRIDGES.find(b => Math.abs(z - b.z) <= b.halfWidth + 0.4);
  if (!bridge) return FIELD.y;
  const across = Math.abs(x - FIELD.xMid);
  if (across > 2.6) return FIELD.y;
  // Ramp on and off the deck instead of stepping up onto it.
  const t = Math.min(1, Math.max(0, (2.6 - across) / 1.1));
  return FIELD.y + (BRIDGE_Y - FIELD.y) * t;
}

export const MATCH = {
  duration: 180,           // three minutes of regular time
  overtime: 120,           // two more if the crowns are level
  elixirMax: 10,
  elixirPerSecond: 1 / 2.8,
  doubleElixirAt: 120,     // last minute of regular time onwards, overtime included
};

// ---------------------------------------------------------------------------
// Units. Ranges and radii are metres; damage is per hit.

export const UNITS = {
  mega_knight: {
    model: { blue: 'mega_knight_blue', red: 'mega_knight_red' },
    height: 2.6, hp: 3400, damage: 300, hitEvery: 1.6, range: 1.5,
    speed: 1.5, radius: 1.0, targets: 'ground', mass: 6,
    splash: 1.9,
    spawnJump: { damage: 220, radius: 2.6 },
    leap: { range: 6.5, cooldown: 9, damage: 260, radius: 2.4 },
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Attack', hit: 'Hit', die: 'Die', jump: 'Jump', smash: 'Smash' },
    attackClip: 'Smash',
  },
  mega_knight_trump: {
    model: { blue: 'mega_knight_trump', red: 'mega_knight_trump' },
    height: 2.9, hp: 5200, damage: 460, hitEvery: 1.5, range: 1.7,
    speed: 1.7, radius: 1.1, targets: 'both', mass: 9,
    splash: 2.4,
    spawnJump: { damage: 380, radius: 3.2 },
    leap: { range: 8.5, cooldown: 7, damage: 420, radius: 3.0 },
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Attack', hit: 'Hit', die: 'Die', jump: 'Jump', smash: 'Smash' },
    attackClip: 'Smash',
  },
  barbarian: {
    model: { blue: 'barbarian', red: 'barbarian' },
    height: 1.9, hp: 700, damage: 160, hitEvery: 1.3, range: 1.1,
    speed: 2.1, radius: 0.55, targets: 'ground', mass: 2,
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Attack', hit: 'Hit', die: 'Die' },
  },
  archer: {
    model: { blue: 'archer_blue', red: 'archer_red' },
    height: 1.6, hp: 300, damage: 110, hitEvery: 1.2, range: 6.5,
    speed: 2.0, radius: 0.45, targets: 'both', mass: 1,
    projectile: { speed: 14, color: 0xffd9a0 },
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Shoot', hit: 'Hit', die: 'Die' },
  },
  princess: {
    // Swapped on purpose: within one army the princess then reads as a
    // different figure from the plain archer, while the team ring and health
    // bar still say which side she is on.
    model: { blue: 'archer_red', red: 'archer_blue' },
    height: 1.6, hp: 220, damage: 150, hitEvery: 2.0, range: 10.5,
    speed: 1.9, radius: 0.45, targets: 'both', mass: 1,
    splash: 1.2,
    projectile: { speed: 12, color: 0xffb060, arc: 2.2 },
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Shoot', hit: 'Hit', die: 'Die' },
  },
  skeleton_archer: {
    model: { blue: 'skeleton_archer', red: 'skeleton_archer' },
    height: 1.45, hp: 150, damage: 70, hitEvery: 1.0, range: 5.5,
    speed: 2.3, radius: 0.4, targets: 'both', mass: 1,
    projectile: { speed: 15, color: 0xd8e4ff },
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Shoot', hit: 'Hit', die: 'Die' },
  },
  hog_rider: {
    model: { blue: 'hog_rider', red: 'hog_rider' },
    height: 2.0, hp: 1400, damage: 250, hitEvery: 1.5, range: 1.3,
    speed: 3.4, radius: 0.6, targets: 'buildings', mass: 3,
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Attack', hit: 'Hit', die: 'Die' },
  },
  baby_dragon: {
    model: { blue: 'baby_dragon', red: 'baby_dragon' },
    height: 1.9, hp: 950, damage: 140, hitEvery: 1.5, range: 5.0,
    speed: 1.9, radius: 0.7, targets: 'both', mass: 3,
    flying: 1.9, splash: 1.4,
    projectile: { speed: 11, color: 0xff9a3c, arc: 1.4 },
    clips: { idle: 'Idle', walk: 'Walk', attack: 'Shoot', hit: 'Hit', die: 'Die' },
  },
};

// ---------------------------------------------------------------------------
// Cards. `count` units are dropped in a small cluster around the tap.

export const CARDS = [
  { id: 'mega_knight', name: 'Мега-Найт', unit: 'mega_knight', art: 'mega_knight_blue', cost: 7, count: 1, rarity: 'legendary' },
  { id: 'hog_rider', name: 'Всадник на кабане', unit: 'hog_rider', art: 'hog_rider', cost: 4, count: 1, rarity: 'rare' },
  { id: 'barbarians', name: 'Варвары', unit: 'barbarian', art: 'barbarian', cost: 5, count: 3, rarity: 'common' },
  { id: 'archers', name: 'Лучницы', unit: 'archer', art: 'archer_blue', cost: 3, count: 2, rarity: 'common' },
  { id: 'princess', name: 'Принцесса', unit: 'princess', art: 'archer_red', cost: 4, count: 1, rarity: 'legendary' },
  { id: 'skeletons', name: 'Скелеты-лучники', unit: 'skeleton_archer', art: 'skeleton_archer', cost: 2, count: 3, rarity: 'common' },
  { id: 'baby_dragon', name: 'Дракончик', unit: 'baby_dragon', art: 'baby_dragon', cost: 4, count: 1, rarity: 'epic' },
  { id: 'trump', name: 'Мега-Найт Трамп', unit: 'mega_knight_trump', art: 'mega_knight_trump', cost: 10, count: 1, rarity: 'champion', chestOnly: true },
];

export const RARITY_COLORS = {
  common: '#9fb4d8', rare: '#ffb648', epic: '#c77dff', legendary: '#6fe3ff', champion: '#ffd24a',
};

// ---------------------------------------------------------------------------

export function isWater(x, z) {
  if (x < RIVER.xMin || x > RIVER.xMax) return false;
  return !BRIDGES.some(b => Math.abs(z - b.z) <= b.halfWidth);
}

export function inField(x, z, margin = 0) {
  return x >= FIELD.xMin + margin && x <= FIELD.xMax - margin
      && z >= FIELD.zMin + margin && z <= FIELD.zMax - margin;
}

/** Ground units may not stand in the river or inside a tower's footprint. */
export function isWalkable(x, z, towers) {
  if (!inField(x, z, 0.2)) return false;
  if (isWater(x, z)) return false;
  for (const t of towers) {
    if (t.dead) continue;
    const r = TOWER_RADIUS[t.kind] + 0.15;
    if ((x - t.x) ** 2 + (z - t.z) ** 2 < r * r) return false;
  }
  return true;
}

/**
 * Where a team may deploy: its own half, never on water or on a tower.
 * As in the original, destroying an enemy princess tower opens up that lane
 * on the far bank, right up to the fallen tower.
 */
export function canDeploy(team, x, z, towers) {
  if (!inField(x, z, 0.6)) return false;
  if (isWater(x, z)) return false;

  let ownSide = team === 'blue' ? x < RIVER.xMin - 0.3 : x > RIVER.xMax + 0.3;
  if (!ownSide) {
    const foe = team === 'blue' ? 'red' : 'blue';
    for (const t of towers) {
      if (t.team !== foe || t.kind !== 'crown' || !t.dead) continue;
      const sameLane = (z < FIELD.zMid) === (t.z < FIELD.zMid);
      const beforeTower = team === 'blue' ? x < t.x : x > t.x;
      if (sameLane && beforeTower) { ownSide = true; break; }
    }
  }
  if (!ownSide) return false;
  for (const t of towers) {
    if (t.dead) continue;
    const r = TOWER_RADIUS[t.kind] + 0.8;
    if ((x - t.x) ** 2 + (z - t.z) ** 2 < r * r) return false;
  }
  return true;
}
