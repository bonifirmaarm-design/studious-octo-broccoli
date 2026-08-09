// Movement: steering with bridge routing, tower avoidance and crowd separation.
//
// A full grid search is overkill here -- the only obstacle a ground unit ever
// has to route around is the river, and it is crossed at exactly two places.
// So the path is "walk to the bridge mouth, cross, then walk to the target",
// which is also how it reads in the original game.

import { BRIDGES, RIVER, TOWER_RADIUS, isWater, FIELD } from './config.js';

const sideOf = x => (x < RIVER.xMin ? -1 : x > RIVER.xMax ? 1 : 0);

/** Bridge whose approach costs least for this unit and destination. */
export function chooseBridge(z, targetZ) {
  let best = BRIDGES[0], bestCost = Infinity;
  for (const bridge of BRIDGES) {
    const cost = Math.abs(z - bridge.z) + Math.abs(targetZ - bridge.z) * 0.6;
    if (cost < bestCost) { bestCost = cost; best = bridge; }
  }
  return best;
}

/**
 * The point a ground unit should steer at right now.
 * Flying units are handed the target unchanged by the caller.
 */
export function steerPoint(unit, targetX, targetZ) {
  const here = sideOf(unit.x);
  const there = sideOf(targetX);

  if (here === 0 || here === there || there === 0) {
    return { x: targetX, z: targetZ };            // same bank, or already crossing
  }

  const bridge = unit.bridge || (unit.bridge = chooseBridge(unit.z, targetZ));
  const approach = here < 0 ? RIVER.xMin - 0.9 : RIVER.xMax + 0.9;
  const exit = here < 0 ? RIVER.xMax + 0.9 : RIVER.xMin - 0.9;

  // Line up with the bridge before stepping onto it, then walk straight across.
  if (Math.abs(unit.z - bridge.z) > bridge.halfWidth * 0.55) {
    return { x: approach, z: bridge.z };
  }
  return { x: exit, z: bridge.z };
}

/** Push a unit out of towers, off the water and back inside the field. */
export function resolveCollisions(unit, towers, others, dt) {
  if (unit.flying) return;

  for (const tower of towers) {
    if (tower.dead) continue;
    const r = TOWER_RADIUS[tower.kind] + unit.radius;
    let dx = unit.x - tower.x, dz = unit.z - tower.z;
    const d2 = dx * dx + dz * dz;
    if (d2 < r * r && d2 > 1e-6) {
      const d = Math.sqrt(d2);
      unit.x = tower.x + (dx / d) * r;
      unit.z = tower.z + (dz / d) * r;
    }
  }

  // Separation: units shoulder each other aside instead of stacking up.
  for (const other of others) {
    if (other === unit || other.dead || other.flying !== unit.flying) continue;
    const r = unit.radius + other.radius;
    let dx = unit.x - other.x, dz = unit.z - other.z;
    let d2 = dx * dx + dz * dz;
    if (d2 >= r * r) continue;
    if (d2 < 1e-6) { dx = Math.random() - 0.5; dz = Math.random() - 0.5; d2 = 0.25; }
    const d = Math.sqrt(d2);
    const push = (r - d) * 0.5 * Math.min(1, other.mass / unit.mass);
    unit.x += (dx / d) * push;
    unit.z += (dz / d) * push;
  }

  if (isWater(unit.x, unit.z)) {
    // Nudge to the nearer bank; a ground unit is never allowed to stand in it.
    const bridge = unit.bridge || chooseBridge(unit.z, unit.z);
    unit.z += Math.sign(bridge.z - unit.z || 1) * Math.min(2.5 * dt + 0.02,
      Math.abs(bridge.z - unit.z) + 0.01);
    if (isWater(unit.x, unit.z)) {
      const toLeft = Math.abs(unit.x - RIVER.xMin), toRight = Math.abs(RIVER.xMax - unit.x);
      unit.x = toLeft < toRight ? RIVER.xMin - 0.05 : RIVER.xMax + 0.05;
    }
  }

  unit.x = Math.min(FIELD.xMax - 0.3, Math.max(FIELD.xMin + 0.3, unit.x));
  unit.z = Math.min(FIELD.zMax - 0.3, Math.max(FIELD.zMin + 0.3, unit.z));
}
