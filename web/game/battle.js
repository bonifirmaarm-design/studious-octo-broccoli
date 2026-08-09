// The simulation: elixir, units, towers, projectiles, win condition.
// Pure state and rules -- nothing in here knows about three.js.

import {
  BRIDGES, BUILDING_DAMAGE_SCALE, CARDS, FIELD, MATCH, RIVER, TOWERS, TOWER_RADIUS,
  UNITS, canDeploy, isWater,
} from './config.js';
import { resolveCollisions, steerPoint } from './nav.js';

let nextId = 1;

const dist2 = (a, b) => (a.x - b.x) ** 2 + (a.z - b.z) ** 2;
const enemyOf = team => (team === 'blue' ? 'red' : 'blue');

export class Tower {
  constructor(spec) {
    Object.assign(this, spec);
    this.id = spec.id;
    this.maxHp = spec.hp;
    this.dead = false;
    this.cooldown = 0;
    this.isTower = true;
    this.radius = TOWER_RADIUS[spec.kind];
    this.flying = false;
    this.mass = 1000;
    // The king defends his tower from the first second. He is not
    // *reachable* until both princess towers are down -- that part is in
    // targetsFor -- but he shoots at anything that comes into range.
    this.active = true;
    this.shotAt = -99;
  }

  damage_(amount) {
    if (this.dead) return;
    this.hp -= amount;
    if (this.hp <= 0) { this.hp = 0; this.dead = true; }
  }
}

export class Unit {
  constructor(type, team, x, z) {
    const spec = UNITS[type];
    this.id = nextId++;
    this.type = type;
    this.spec = spec;
    this.team = team;
    this.x = x;
    this.z = z;
    this.hp = spec.hp;
    this.maxHp = spec.hp;
    this.radius = spec.radius;
    this.mass = spec.mass || 1;
    this.flying = spec.flying || 0;
    this.speed = spec.speed;
    this.facing = team === 'blue' ? 0 : Math.PI;
    this.cooldown = spec.hitEvery * 0.4;
    this.state = 'spawn';
    this.stateTime = 0;
    this.target = null;
    this.bridge = null;
    this.dead = false;
    this.deathTime = 0;
    this.leapCooldown = spec.leap ? 2.5 : Infinity;
    this.leap = null;
    this.flash = 0;
  }

  get canHit() { return this.spec.targets; }

  damage_(amount) {
    if (this.dead) return;
    this.hp -= amount;
    this.flash = 0.18;
    if (this.hp <= 0) {
      this.hp = 0;
      this.dead = true;
      this.state = 'die';
      this.stateTime = 0;
    }
  }
}

export class Projectile {
  constructor(from, to, spec, damage, team, splash) {
    this.id = nextId++;
    this.x = from.x; this.y = from.y; this.z = from.z;
    this.target = to;
    this.speed = spec.speed;
    this.arc = spec.arc || 0;
    this.color = spec.color;
    this.damage = damage;
    this.team = team;
    this.splash = splash || 0;
    this.done = false;
    this.t = 0;
    this.start = { ...from };
  }
}

export class Battle {
  constructor(deck, options = {}) {
    this.towers = TOWERS.map(spec => new Tower({ ...spec }));
    this.units = [];
    this.projectiles = [];
    this.effects = [];
    this.time = 0;
    this.over = null;
    this.elixir = { blue: 5, red: 5 };
    this.deck = deck;
    this.crowns = { blue: 0, red: 0 };
    this.onEvent = options.onEvent || (() => {});
  }

  towersOf(team) { return this.towers.filter(t => t.team === team && !t.dead); }

  elixirRate() {
    return MATCH.elixirPerSecond * (this.time >= MATCH.doubleElixirAt ? 2 : 1);
  }

  canPlay(team, card, x, z) {
    if (this.over) return false;
    if (this.elixir[team] < card.cost) return false;
    return canDeploy(team, x, z, this.towers);
  }

  play(team, card, x, z) {
    if (!this.canPlay(team, card, x, z)) return false;
    this.elixir[team] -= card.cost;
    this.spawn(card, team, x, z);
    return true;
  }

  spawn(card, team, x, z) {
    const spread = card.count > 1 ? 0.85 : 0;
    for (let i = 0; i < card.count; i++) {
      const angle = (i / card.count) * Math.PI * 2;
      const ux = x + Math.cos(angle) * spread;
      const uz = z + Math.sin(angle) * spread;
      const unit = new Unit(card.unit, team, ux, uz);
      this.units.push(unit);
      this.onEvent({ type: 'spawn', unit });

      // The Mega Knights land from above and shake the ground on arrival.
      const jump = unit.spec.spawnJump;
      if (jump) {
        unit.state = 'jumpIn';
        unit.stateTime = 0;
        unit.jumpFrom = 6.0;
      }
    }
  }

  // -------------------------------------------------------------- targeting

  targetsFor(unit) {
    const foe = enemyOf(unit.team);
    const list = [];
    if (unit.spec.targets !== 'buildings') {
      for (const other of this.units) {
        if (other.dead || other.team !== foe) continue;
        if (other.flying && unit.spec.targets === 'ground') continue;
        list.push(other);
      }
    }
    for (const tower of this.towers) {
      if (tower.dead || tower.team !== foe) continue;
      if (tower.kind === 'king' && this.towersOf(foe).some(t => t.kind === 'crown')) {
        continue;      // the two princess towers have to go down first
      }
      list.push(tower);
    }
    return list;
  }

  pickTarget(unit) {
    const candidates = this.targetsFor(unit);
    let best = null, bestScore = Infinity;
    for (const c of candidates) {
      const d = Math.sqrt(dist2(unit, c));
      // Buildings-only units ignore everything else; others slightly prefer troops.
      const score = d + (c.isTower ? 3.5 : 0);
      if (score < bestScore) { bestScore = score; best = c; }
    }
    return best;
  }

  // ------------------------------------------------------------------ ticks

  update(dt) {
    if (this.over) return;
    this.time += dt;

    for (const team of ['blue', 'red']) {
      this.elixir[team] = Math.min(MATCH.elixirMax, this.elixir[team] + this.elixirRate() * dt);
    }

    for (const unit of this.units) this.updateUnit(unit, dt);
    for (const tower of this.towers) this.updateTower(tower, dt);
    this.updateProjectiles(dt);

    this.effects = this.effects.filter(e => (e.life -= dt) > 0);
    this.units = this.units.filter(u => !(u.dead && u.deathTime > 1.6));

    this.checkEnd();
  }

  updateUnit(unit, dt) {
    unit.stateTime += dt;
    unit.flash = Math.max(0, unit.flash - dt);
    if (unit.dead) { unit.deathTime += dt; return; }

    // Landing from the deploy jump.
    if (unit.state === 'jumpIn') {
      const total = 0.85;
      if (unit.stateTime >= total) {
        const jump = unit.spec.spawnJump;
        this.areaDamage(unit, unit.x, unit.z, jump.radius, jump.damage);
        this.effects.push({ type: 'shock', x: unit.x, z: unit.z, r: jump.radius, life: 0.45, max: 0.45 });
        unit.state = 'idle';
        unit.stateTime = 0;
      }
      return;
    }

    // Mid-leap: fly along the arc, then slam down.
    if (unit.state === 'leap') {
      const leap = unit.leap;
      leap.t += dt / leap.duration;
      if (leap.t >= 1) {
        unit.x = leap.tx; unit.z = leap.tz;
        this.areaDamage(unit, unit.x, unit.z, unit.spec.leap.radius, unit.spec.leap.damage);
        this.effects.push({ type: 'shock', x: unit.x, z: unit.z, r: unit.spec.leap.radius,
                            life: 0.5, max: 0.5 });
        unit.state = 'idle';
        unit.stateTime = 0;
        unit.leap = null;
      } else {
        const travel = Math.max(0, (leap.t - leap.liftOff) / (1 - leap.liftOff));
        unit.x = leap.fx + (leap.tx - leap.fx) * travel;
        unit.z = leap.fz + (leap.tz - leap.fz) * travel;
      }
      return;
    }

    unit.cooldown -= dt;
    unit.leapCooldown -= dt;

    if (!unit.target || unit.target.dead || (unit.target.hp !== undefined && unit.target.hp <= 0)) {
      unit.target = this.pickTarget(unit);
      unit.bridge = null;
    }
    const target = unit.target;
    if (!target) { unit.state = 'idle'; return; }

    const reach = unit.spec.range + (target.radius || 0);
    const gap = Math.sqrt(dist2(unit, target));

    // A Mega Knight in range of a distant group leaps onto it.
    const leapSpec = unit.spec.leap;
    if (leapSpec && unit.leapCooldown <= 0 && gap > reach + 2.0 && gap < leapSpec.range
        && !target.flying) {
      unit.state = 'leap';
      unit.stateTime = 0;
      unit.leapCooldown = leapSpec.cooldown;
      // Timed against the Jump clip: it crouches until 0.48 s and lands at
      // 1.28 s, so the body only travels over that stretch. The clip lifts the
      // model itself, which is why no extra height is added here.
      unit.leap = {
        fx: unit.x, fz: unit.z, tx: target.x, tz: target.z,
        t: 0, duration: 1.28, liftOff: 0.48 / 1.28, height: 0,
      };
      unit.facing = Math.atan2(target.x - unit.x, target.z - unit.z);
      return;
    }

    if (gap <= reach) {
      unit.state = 'attack';
      unit.facing = Math.atan2(target.x - unit.x, target.z - unit.z);
      if (unit.cooldown <= 0) {
        unit.cooldown = unit.spec.hitEvery;
        unit.attackAt = this.time;
        this.strike(unit, target);
      }
      return;
    }

    // Walk.
    const aim = unit.flying ? { x: target.x, z: target.z } : steerPoint(unit, target.x, target.z);
    const dx = aim.x - unit.x, dz = aim.z - unit.z;
    const d = Math.hypot(dx, dz) || 1;
    const step = unit.speed * dt;
    unit.x += (dx / d) * step;
    unit.z += (dz / d) * step;
    unit.facing = Math.atan2(dx, dz);
    unit.state = 'walk';

    resolveCollisions(unit, this.towers, this.units, dt);
  }

  strike(unit, target) {
    const projectile = unit.spec.projectile;
    if (projectile) {
      const from = { x: unit.x, y: FIELD.y + unit.spec.height * 0.65 + (unit.flying || 0), z: unit.z };
      this.projectiles.push(new Projectile(from, target, projectile,
                                           unit.spec.damage, unit.team, unit.spec.splash));
      return;
    }
    if (unit.spec.splash) {
      this.areaDamage(unit, target.x, target.z, unit.spec.splash, unit.spec.damage);
    } else {
      this.hit(target, unit.spec.damage);
    }
  }

  areaDamage(source, x, z, radius, damage) {
    const foe = enemyOf(source.team);
    for (const other of this.units) {
      if (other.dead || other.team !== foe) continue;
      if (other.flying && source.spec && source.spec.targets === 'ground') continue;
      if ((other.x - x) ** 2 + (other.z - z) ** 2 <= radius * radius) this.hit(other, damage);
    }
    for (const tower of this.towers) {
      if (tower.dead || tower.team !== foe) continue;
      const r = radius + tower.radius;
      if ((tower.x - x) ** 2 + (tower.z - z) ** 2 <= r * r) this.hit(tower, damage);
    }
  }

  hit(entity, damage) {
    if (!entity || entity.dead) return;
    entity.damage_(entity.isTower ? damage * BUILDING_DAMAGE_SCALE : damage);
    if (entity.isTower) {
      if (entity.dead) {
        this.crowns[enemyOf(entity.team)] += entity.kind === 'king' ? 3 : 1;
        this.onEvent({ type: 'towerDown', tower: entity });
      }
    } else if (entity.dead) {
      this.onEvent({ type: 'death', unit: entity });
    }
  }

  updateTower(tower, dt) {
    if (tower.dead) return;
    tower.cooldown -= dt;

    const foe = enemyOf(tower.team);
    let best = null, bestD = Infinity;
    for (const unit of this.units) {
      if (unit.dead || unit.team !== foe) continue;
      const d = dist2(tower, unit);
      if (d < bestD) { bestD = d; best = unit; }
    }
    const range = tower.range + (best ? best.radius : 0);
    if (best && bestD <= range * range && tower.cooldown <= 0) {
      tower.cooldown = tower.hitEvery;
      tower.shotAt = this.time;
      this.projectiles.push(new Projectile(
        { x: tower.x, y: FIELD.y + (tower.kind === 'king' ? 3.2 : 2.4), z: tower.z },
        best, { speed: 16, color: tower.team === 'blue' ? 0x7ec8ff : 0xff8a7a },
        tower.damage, tower.team, 0));
    }
  }

  updateProjectiles(dt) {
    for (const p of this.projectiles) {
      const target = p.target;
      if (!target || target.dead) { p.done = true; continue; }
      const ty = FIELD.y + (target.isTower ? 1.6 : (target.spec.height * 0.5 + (target.flying || 0)));
      const dx = target.x - p.x, dy = ty - p.y, dz = target.z - p.z;
      const d = Math.hypot(dx, dy, dz);
      const step = p.speed * dt;
      p.t += dt;
      if (d <= step) {
        if (p.splash) {
          this.areaDamage({ team: p.team }, target.x, target.z, p.splash, p.damage);
          this.effects.push({ type: 'burst', x: target.x, z: target.z, r: p.splash,
                              life: 0.3, max: 0.3, color: p.color });
        } else {
          this.hit(target, p.damage);
        }
        p.done = true;
      } else {
        p.x += (dx / d) * step;
        p.y += (dy / d) * step + (p.arc ? Math.sin(Math.min(1, p.t * 2) * Math.PI) * p.arc * dt : 0);
        p.z += (dz / d) * step;
      }
    }
    this.projectiles = this.projectiles.filter(p => !p.done);
  }

  checkEnd() {
    // The match runs until one side has lost ALL THREE towers, not just its
    // king tower.
    for (const team of ['blue', 'red']) {
      if (this.towers.every(t => t.team !== team || t.dead)) {
        this.finish(enemyOf(team), 'Все три башни разрушены');
        return;
      }
    }
    const limit = MATCH.duration + MATCH.overtime;
    if (this.time >= MATCH.duration && this.crowns.blue !== this.crowns.red) {
      this.finish(this.crowns.blue > this.crowns.red ? 'blue' : 'red', 'По коронам');
    } else if (this.time >= limit) {
      const lowest = team => Math.min(...this.towers.filter(t => t.team === team)
        .map(t => t.hp / t.maxHp));
      const blue = lowest('blue'), red = lowest('red');
      if (blue === red) this.finish(null, 'Ничья');
      else this.finish(blue > red ? 'blue' : 'red', 'По остатку прочности');
    }
  }

  finish(winner, reason) {
    this.over = { winner, reason };
    this.onEvent({ type: 'over', winner, reason });
  }
}

export function findCard(id) {
  return CARDS.find(c => c.id === id);
}
