// Everything three.js: loading the arena and unit models, spawning instances,
// driving their animation mixers, health bars, projectiles and hit effects.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { clone as cloneSkinned } from 'three/addons/utils/SkeletonUtils.js';
import { FIELD, KING_MODELS, TOWER_RADIUS, UNITS } from './config.js';

const loader = new GLTFLoader();
const load = url => new Promise((res, rej) => loader.load(url, res, undefined, rej));

const TEAM_COLOR = { blue: 0x4a86ff, red: 0xff4d4d };

export class View {
  constructor(scene) {
    this.scene = scene;
    this.prototypes = new Map();
    this.actors = new Map();
    this.projectiles = new Map();
    this.effects = [];
    this.mixers = [];
    this.group = new THREE.Group();
    scene.add(this.group);

    this.projectileGeometry = new THREE.SphereGeometry(0.13, 10, 8);
    this.shockGeometry = new THREE.RingGeometry(0.55, 1.0, 40);
  }

  async loadArena(url) {
    const gltf = await load(url);
    gltf.scene.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    this.scene.add(gltf.scene);
    return gltf.scene;
  }

  async loadUnits(keys, onProgress) {
    let done = 0;
    for (const key of keys) {
      const gltf = await load(`./assets/units/${key}.glb`);
      this.prototypes.set(key, gltf);
      onProgress?.(++done, keys.length, key);
    }
  }

  modelKeyFor(type, team) {
    return UNITS[type].model[team];
  }

  // -------------------------------------------------------------- instances

  makeActor(key, height) {
    const proto = this.prototypes.get(key);
    const root = new THREE.Group();
    const model = cloneSkinned(proto.scene);
    model.traverse(o => {
      if (o.isMesh || o.isSkinnedMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
        o.frustumCulled = false;
        o.material = o.material.clone();
      }
    });
    root.add(model);
    root.scale.setScalar(height);

    const mixer = new THREE.AnimationMixer(model);
    const actions = new Map();
    for (const clip of proto.animations) {
      const action = mixer.clipAction(clip);
      actions.set(clip.name, action);
    }
    this.mixers.push(mixer);
    this.group.add(root);
    return { root, model, mixer, actions, current: null, currentName: null };
  }

  play(actor, name, { loop = true, fade = 0.16, speed = 1 } = {}) {
    const action = actor.actions.get(name);
    if (!action || actor.currentName === name) return;
    action.reset();
    action.setEffectiveTimeScale(speed);
    action.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, loop ? Infinity : 1);
    action.clampWhenFinished = !loop;
    if (actor.current) actor.current.fadeOut(fade);
    action.fadeIn(fade).play();
    actor.current = action;
    actor.currentName = name;
  }

  /** One-shot clip that returns to whatever loops afterwards. */
  trigger(actor, name, speed = 1) {
    const action = actor.actions.get(name);
    if (!action) return;
    action.reset();
    action.setEffectiveTimeScale(speed);
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    if (actor.current && actor.current !== action) actor.current.fadeOut(0.08);
    action.fadeIn(0.06).play();
    actor.current = action;
    actor.currentName = name;
  }

  // ------------------------------------------------------------ health bars

  makeBar(width, team) {
    // Both halves must live in the same render queue: an opaque fill would be
    // drawn before the transparent backing and end up hidden behind it.
    const group = new THREE.Group();
    const back = new THREE.Mesh(
      new THREE.PlaneGeometry(width, width * 0.16),
      new THREE.MeshBasicMaterial({ color: 0x0b0e18, transparent: true, opacity: 0.8,
                                    depthTest: false, depthWrite: false }));
    const fill = new THREE.Mesh(
      new THREE.PlaneGeometry(width, width * 0.16),
      new THREE.MeshBasicMaterial({ color: TEAM_COLOR[team], transparent: true, opacity: 1,
                                    depthTest: false, depthWrite: false }));
    back.renderOrder = 998;
    fill.renderOrder = 999;
    fill.position.z = 0.002;
    group.add(back, fill);
    group.userData = { fill, width };
    return group;
  }

  /** Team-coloured disc under a unit, so sides read at a glance. */
  makeFootRing(radius, team) {
    const mesh = new THREE.Mesh(
      new THREE.RingGeometry(radius * 0.9, radius * 1.25, 28),
      new THREE.MeshBasicMaterial({ color: TEAM_COLOR[team], transparent: true,
                                    opacity: 0.55, side: THREE.DoubleSide,
                                    depthWrite: false }));
    mesh.rotation.x = -Math.PI / 2;
    return mesh;
  }

  setBar(group, fraction) {
    const { fill, width } = group.userData;
    const clamped = Math.max(0, Math.min(1, fraction));
    fill.scale.x = clamped || 0.0001;
    fill.position.x = -width * (1 - clamped) / 2;
  }

  // -------------------------------------------------------------- towers

  buildTowers(towers) {
    this.towerViews = new Map();
    for (const tower of towers) {
      const group = new THREE.Group();
      const bar = this.makeBar(tower.kind === 'king' ? 2.6 : 2.0, tower.team);
      bar.position.set(tower.x, FIELD.y + (tower.kind === 'king' ? 4.6 : 3.4), tower.z);
      this.group.add(bar);

      let king = null;
      if (tower.kind === 'king' && this.prototypes.has(KING_MODELS[tower.team])) {
        king = this.makeActor(KING_MODELS[tower.team], 2.1);
        king.root.position.set(tower.x, FIELD.y + 2.6, tower.z + (tower.team === 'blue' ? 0.1 : -0.1));
        king.root.rotation.y = tower.team === 'blue' ? Math.PI / 2 : -Math.PI / 2;
        this.play(king, 'Idle');
      }
      this.towerViews.set(tower.id, { bar, king, group });
      void group;
    }
  }

  updateTowers(towers, camera) {
    for (const tower of towers) {
      const view = this.towerViews.get(tower.id);
      if (!view) continue;
      this.setBar(view.bar, tower.hp / tower.maxHp);
      view.bar.visible = !tower.dead;
      view.bar.quaternion.copy(camera.quaternion);
      if (view.king) {
        view.king.root.visible = !tower.dead;
        if (tower.dead && view.king.currentName !== 'Die') this.trigger(view.king, 'Die');
        else if (!tower.dead && this.now - (tower.shotAt ?? -99) < 0.12) {
          this.trigger(view.king, 'Shoot');
        }
      }
    }
  }

  // --------------------------------------------------------------- units

  syncUnits(units, camera, dt) {
    const seen = new Set();
    for (const unit of units) {
      seen.add(unit.id);
      let actor = this.actors.get(unit.id);
      if (!actor) {
        const key = this.modelKeyFor(unit.type, unit.team);
        actor = this.makeActor(key, unit.spec.height);
        actor.bar = this.makeBar(Math.max(0.9, unit.spec.height * 0.5), unit.team);
        actor.ring = this.makeFootRing(Math.max(0.4, unit.radius), unit.team);
        this.group.add(actor.bar, actor.ring);
        actor.tint = new THREE.Color(TEAM_COLOR[unit.team]);
        this.actors.set(unit.id, actor);
        this.play(actor, unit.spec.clips.idle);
      }

      let y = FIELD.y + (unit.flying || 0);
      if (unit.state === 'jumpIn') {
        const t = Math.min(1, unit.stateTime / 0.85);
        y += (1 - t) * (1 - t) * unit.jumpFrom;
      } else if (unit.state === 'leap' && unit.leap) {
        const t = unit.leap.t;
        y += Math.sin(Math.PI * t) * unit.leap.height;
      }

      actor.root.position.set(unit.x, y, unit.z);
      actor.root.rotation.y = unit.facing;

      const clips = unit.spec.clips;
      if (unit.dead) {
        this.play(actor, clips.die, { loop: false, fade: 0.1 });
      } else if (unit.state === 'leap' || unit.state === 'jumpIn') {
        this.play(actor, clips.jump || clips.idle, { loop: false, fade: 0.08 });
      } else if (unit.state === 'attack') {
        const name = unit.spec.attackClip && actor.actions.has(unit.spec.attackClip)
          ? unit.spec.attackClip : clips.attack;
        if (unit.attackAt !== undefined && this.now - unit.attackAt < 0.06) {
          this.trigger(actor, name, Math.min(2.2, 1.1 / unit.spec.hitEvery));
        } else if (!actor.current || !actor.current.isRunning()) {
          this.play(actor, clips.idle);
        }
      } else if (unit.state === 'walk') {
        this.play(actor, clips.walk, { speed: Math.max(0.7, unit.speed / 2.0) });
      } else {
        if (!actor.currentName || actor.currentName === clips.walk) this.play(actor, clips.idle);
      }

      // Damage flash.
      const flash = unit.flash > 0 ? unit.flash / 0.18 : 0;
      actor.model.traverse(o => {
        if (o.isMesh || o.isSkinnedMesh) {
          o.material.emissive?.setRGB(flash * 0.55, flash * 0.06, flash * 0.06);
        }
      });

      actor.ring.visible = !unit.dead && !unit.flying;
      actor.ring.position.set(unit.x, FIELD.y + 0.05, unit.z);

      actor.bar.visible = !unit.dead;
      actor.bar.position.set(unit.x, y + unit.spec.height * 1.08, unit.z);
      actor.bar.quaternion.copy(camera.quaternion);
      this.setBar(actor.bar, unit.hp / unit.maxHp);
    }

    for (const [id, actor] of this.actors) {
      if (seen.has(id)) continue;
      this.group.remove(actor.root, actor.bar, actor.ring);
      this.mixers = this.mixers.filter(m => m !== actor.mixer);
      actor.mixer.stopAllAction();
      this.actors.delete(id);
    }
    void dt;
  }

  // ---------------------------------------------------- projectiles, effects

  syncProjectiles(projectiles) {
    const seen = new Set();
    for (const p of projectiles) {
      seen.add(p.id);
      let mesh = this.projectiles.get(p.id);
      if (!mesh) {
        mesh = new THREE.Mesh(this.projectileGeometry,
          new THREE.MeshBasicMaterial({ color: p.color }));
        this.group.add(mesh);
        this.projectiles.set(p.id, mesh);
      }
      mesh.position.set(p.x, p.y, p.z);
    }
    for (const [id, mesh] of this.projectiles) {
      if (seen.has(id)) continue;
      this.group.remove(mesh);
      mesh.material.dispose();
      this.projectiles.delete(id);
    }
  }

  syncEffects(effects) {
    for (const mesh of this.effects) this.group.remove(mesh);
    this.effects.length = 0;
    for (const e of effects) {
      const t = 1 - e.life / e.max;
      const mesh = new THREE.Mesh(this.shockGeometry, new THREE.MeshBasicMaterial({
        color: e.color ?? 0xffe9a8, transparent: true, opacity: (1 - t) * 0.8,
        side: THREE.DoubleSide, depthWrite: false,
      }));
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set(e.x, FIELD.y + 0.06, e.z);
      mesh.scale.setScalar(e.r * (0.35 + t));
      this.group.add(mesh);
      this.effects.push(mesh);
    }
  }

  update(dt, now) {
    this.now = now;
    for (const mixer of this.mixers) mixer.update(dt);
  }
}

export { TEAM_COLOR, TOWER_RADIUS };
