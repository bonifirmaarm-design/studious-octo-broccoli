"""Render each unit to a transparent PNG for its card face.

The card art is a screenshot of the actual model in a readable pose, lit
brightly and trimmed to its silhouette, so the deck always matches the units
that walk onto the field.
"""

import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render import CHROME, Server
from roster import ROSTER

SIZE = (420, 480)
OUT = "web/assets/cards"

# Card poses: a moment that reads as the unit's identity.
POSES = {
    "mega_knight_blue": ("Smash", 0.36),
    "mega_knight_red": ("Smash", 0.36),
    "mega_knight_trump": ("Smash", 0.36),
    "barbarian": ("Attack", 0.26),
    "archer_blue": ("Shoot", 0.50),
    "archer_red": ("Shoot", 0.50),
    "skeleton_archer": ("Shoot", 0.50),
    "hog_rider": ("Walk", 0.16),
    "baby_dragon": ("Idle", 0.25),
    "king_blue": ("Idle", 0.0),
    "king_red": ("Idle", 0.0),
}

PAGE = """
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:transparent}canvas{display:block}
</style></head><body>
<script type="importmap">{"imports":{
"three":"/node_modules/three/build/three.module.js",
"three/addons/":"/node_modules/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const p = new URLSearchParams(location.search);
const W = +p.get('w'), H = +p.get('h');
const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true, preserveDrawingBuffer:true});
renderer.setSize(W, H); renderer.setPixelRatio(1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xffffff, 0x606a80, 2.6));
const key = new THREE.DirectionalLight(0xffffff, 2.6); key.position.set(3,6,7); scene.add(key);
const fill = new THREE.DirectionalLight(0xbcd8ff, 1.2); fill.position.set(-5,2,3); scene.add(fill);
const back = new THREE.DirectionalLight(0xffe0b0, 1.4); back.position.set(0,4,-6); scene.add(back);

const camera = new THREE.PerspectiveCamera(30, W/H, 0.01, 100);
let mixer=null, model=null, clips=[];
window.state = {ready:false};
new GLTFLoader().load(p.get('src'), g => {
  model = g.scene; scene.add(model); clips = g.animations || [];
  model.traverse(o => { if (o.isMesh||o.isSkinnedMesh) o.frustumCulled = false; });
  if (clips.length) mixer = new THREE.AnimationMixer(model);
  window.state.ready = true;
}, undefined, e => { window.state.error = String(e); });

window.pose = (name, t) => {
  if (!mixer) return;
  const clip = clips.find(c => c.name === name);
  if (!clip) return;
  mixer.stopAllAction();
  mixer.clipAction(clip).play();
  mixer.setTime(0); mixer.setTime(t);
};
window.frame = () => {
  model.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(model, true);
  const size = box.getSize(new THREE.Vector3());
  const centre = box.getCenter(new THREE.Vector3());
  const r = Math.max(size.x, size.y * 0.92, size.z);
  const dir = new THREE.Vector3(0.55, 0.22, 1).normalize();
  camera.position.copy(centre).addScaledVector(dir, r * 3.0);
  camera.lookAt(centre);
  camera.updateProjectionMatrix();
};
window.draw = () => renderer.render(scene, camera);
</script></body></html>
"""


def trim(path, pad=10):
    image = Image.open(path).convert("RGBA")
    bbox = image.split()[3].getbbox()
    if not bbox:
        return
    left, top, right, bottom = bbox
    left, top = max(0, left - pad), max(0, top - pad)
    right, bottom = min(image.width, right + pad), min(image.height, bottom + pad)
    image.crop((left, top, right, bottom)).save(path)


def main(keys=None):
    keys = keys or list(ROSTER)
    mounts = {"/__card.html": (PAGE, "text/html")}
    for key in keys:
        with open(f"web/assets/units/{key}.glb", "rb") as fh:
            mounts[f"/{key}.glb"] = (fh.read(), "model/gltf-binary")
    server = Server(extra=mounts)
    os.makedirs(OUT, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME,
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page = browser.new_page(viewport={"width": SIZE[0], "height": SIZE[1]})
        for key in keys:
            page.goto(f"http://127.0.0.1:{server.port}/__card.html"
                      f"?src=/{key}.glb&w={SIZE[0]}&h={SIZE[1]}")
            page.wait_for_function("window.state && (window.state.ready || window.state.error)",
                                   timeout=120000)
            clip, t = POSES.get(key, ("Idle", 0.0))
            page.evaluate(f"window.pose('{clip}', {t})")
            page.evaluate("window.frame()")
            page.evaluate("window.draw()")
            path = f"{OUT}/{key}.png"
            page.locator("canvas").screenshot(path=path, omit_background=True)
            trim(path)
            print("card", key, os.path.getsize(path) // 1024, "KB")
        browser.close()
    server.stop()


if __name__ == "__main__":
    main(sys.argv[1:] or None)
