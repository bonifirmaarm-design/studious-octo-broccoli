// Two camera modes: a fixed battle view, and a Minecraft-style free flight
// that is clamped to the arena so you can never lose the map.

import * as THREE from 'three';
import { FIELD } from './config.js';

const BOUNDS = {
  xMin: FIELD.xMin - 14, xMax: FIELD.xMax + 14,
  zMin: FIELD.zMin - 16, zMax: FIELD.zMax + 16,
  yMin: FIELD.y + 0.8, yMax: FIELD.y + 42,
};

// Chosen so the near wall of the stadium stays out of frame: the seating
// decks are 8 m tall and reach 17 m out from the touchline.
export const VIEWS = {
  battle: { pos: [FIELD.xMid, 31, 32], look: [FIELD.xMid, FIELD.y, 0] },
  blue: { pos: [FIELD.xMin - 3, 20, 22], look: [FIELD.xMid - 7, FIELD.y, 0] },
  red: { pos: [FIELD.xMax + 3, 20, 22], look: [FIELD.xMid + 7, FIELD.y, 0] },
  top: { pos: [FIELD.xMid, 40, 0.01], look: [FIELD.xMid, FIELD.y, 0] },
};

export class CameraRig {
  constructor(camera, domElement) {
    this.camera = camera;
    this.dom = domElement;
    this.free = false;
    this.speed = 11;
    this.keys = new Set();
    this.yaw = 0;
    this.pitch = -0.6;
    this.dragging = false;

    this.setView('battle');

    addEventListener('keydown', e => {
      if (e.repeat) return;
      this.keys.add(e.code);
      if (e.code === 'KeyF' && !isTyping(e)) this.toggleFree();
    });
    addEventListener('keyup', e => this.keys.delete(e.code));
    addEventListener('blur', () => this.keys.clear());

    domElement.addEventListener('pointerdown', e => {
      if (e.button === 2 || (this.free && e.button === 0 && e.shiftKey)) {
        this.dragging = true;
        domElement.setPointerCapture(e.pointerId);
      }
    });
    domElement.addEventListener('pointerup', e => {
      this.dragging = false;
      if (domElement.hasPointerCapture(e.pointerId)) domElement.releasePointerCapture(e.pointerId);
    });
    domElement.addEventListener('pointermove', e => {
      if (!this.dragging) return;
      this.yaw -= e.movementX * 0.0032;
      this.pitch = clamp(this.pitch - e.movementY * 0.0032, -1.45, 1.35);
      this.applyAngles();
    });
    domElement.addEventListener('contextmenu', e => e.preventDefault());
    domElement.addEventListener('wheel', e => {
      e.preventDefault();
      if (this.free) { this.speed = clamp(this.speed * (e.deltaY > 0 ? 0.9 : 1.1), 2, 60); return; }
      const dir = new THREE.Vector3();
      this.camera.getWorldDirection(dir);
      this.camera.position.addScaledVector(dir, e.deltaY > 0 ? -2.4 : 2.4);
      this.clampPosition();
    }, { passive: false });
  }

  setView(name) {
    const view = VIEWS[name] || VIEWS.battle;
    this.camera.position.set(...view.pos);
    this.camera.lookAt(new THREE.Vector3(...view.look));
    this.syncAngles();
  }

  toggleFree(on = !this.free) {
    this.free = on;
    if (on) this.syncAngles();
    this.dom.style.cursor = on ? 'crosshair' : 'default';
    return this.free;
  }

  syncAngles() {
    const dir = new THREE.Vector3();
    this.camera.getWorldDirection(dir);
    this.yaw = Math.atan2(-dir.x, -dir.z);
    this.pitch = Math.asin(clamp(dir.y, -1, 1));
  }

  applyAngles() {
    const dir = new THREE.Vector3(
      -Math.sin(this.yaw) * Math.cos(this.pitch),
      Math.sin(this.pitch),
      -Math.cos(this.yaw) * Math.cos(this.pitch),
    );
    this.camera.lookAt(this.camera.position.clone().add(dir));
  }

  clampPosition() {
    const p = this.camera.position;
    p.x = clamp(p.x, BOUNDS.xMin, BOUNDS.xMax);
    p.y = clamp(p.y, BOUNDS.yMin, BOUNDS.yMax);
    p.z = clamp(p.z, BOUNDS.zMin, BOUNDS.zMax);
  }

  update(dt) {
    if (!this.free) return;
    const forward = new THREE.Vector3();
    this.camera.getWorldDirection(forward);
    const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();

    const move = new THREE.Vector3();
    if (this.keys.has('KeyW')) move.add(forward);
    if (this.keys.has('KeyS')) move.sub(forward);
    if (this.keys.has('KeyD')) move.add(right);
    if (this.keys.has('KeyA')) move.sub(right);
    if (this.keys.has('Space')) move.y += 1;
    if (this.keys.has('ShiftLeft') || this.keys.has('ControlLeft')) move.y -= 1;
    if (move.lengthSq() === 0) return;

    move.normalize().multiplyScalar(this.speed * dt * (this.keys.has('KeyR') ? 2.5 : 1));
    this.camera.position.add(move);
    this.clampPosition();
    this.applyAngles();
  }
}

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function isTyping(e) {
  const el = e.target;
  return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
}
