"""Offscreen screenshot tool: loads a GLB in headless Chromium + three.js.

Usage:
    python3 tools/render.py model.glb out_prefix [--views front,top,iso] [--anim Punch@0.4]
"""

import argparse
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The pre-installed browser; the pip playwright build expects a different revision.
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

PAGE = """
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:#20242e;overflow:hidden}canvas{display:block}
</style></head><body>
<script type="importmap">{"imports":{
"three":"/node_modules/three/build/three.module.js",
"three/addons/":"/node_modules/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const params = new URLSearchParams(location.search);
const W = +(params.get('w') || 900), H = +(params.get('h') || 700);

const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setSize(W, H);
renderer.setPixelRatio(1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x20242e);
scene.add(new THREE.HemisphereLight(0xffffff, 0x4a4a5a, 2.2));
const key = new THREE.DirectionalLight(0xffffff, 2.0);
key.position.set(4, 8, 6); scene.add(key);
const fill = new THREE.DirectionalLight(0xaaccff, 0.8);
fill.position.set(-5, 3, -4); scene.add(fill);
scene.add(new THREE.GridHelper(20, 20, 0x556677, 0x333944));
const axes = new THREE.AxesHelper(2); scene.add(axes);

const camera = new THREE.PerspectiveCamera(35, W/H, 0.01, 5000);
let mixer = null, model = null, box = null, clips = [];

window.state = {ready:false, info:null};

new GLTFLoader().load(params.get('src'), (gltf) => {
  model = gltf.scene;
  scene.add(model);
  clips = gltf.animations || [];
  box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const names = [];
  model.traverse(o => { if (o.isMesh || o.isSkinnedMesh) names.push(o.name); });
  window.state.info = {
    size: size.toArray(), center: center.toArray(),
    min: box.min.toArray(), max: box.max.toArray(),
    meshes: names, animations: clips.map(c => [c.name, c.duration]),
  };
  if (clips.length) { mixer = new THREE.AnimationMixer(model); }
  window.state.ready = true;
}, undefined, (err) => { window.state.error = String(err && err.message || err); });

window.setView = (view, zoom) => {
  // Re-measure every time: an animated pose can sit well outside the rest box.
  model.updateMatrixWorld(true);
  // `precise` walks the skinned vertices; without it the box ignores the pose.
  const live = new THREE.Box3().setFromObject(model, true);
  const size = live.getSize(new THREE.Vector3());
  const center = live.getCenter(new THREE.Vector3());
  const r = Math.max(size.x, size.y, size.z) * (zoom || 1.0);
  const dirs = {
    front: [0, 0.15, 1], back: [0, 0.15, -1], left: [-1, 0.15, 0], right: [1, 0.15, 0],
    top: [0, 1, 0.001], iso: [1, 0.8, 1], iso2: [-1, 0.6, 1], low: [0.6, 0.12, 1],
  };
  const d = new THREE.Vector3(...(dirs[view] || dirs.iso)).normalize();
  camera.position.copy(center).addScaledVector(d, r * 1.9);
  camera.lookAt(center);
  camera.updateProjectionMatrix();
};

window.playAt = (name, t) => {
  if (!mixer) return false;
  const clip = clips.find(c => c.name === name);
  if (!clip) return false;
  mixer.stopAllAction();
  const action = mixer.clipAction(clip);
  action.play();
  mixer.setTime(0);
  mixer.setTime(t);
  return true;
};

window.showAxes = (on) => { axes.visible = on; };
window.draw = () => { renderer.render(scene, camera); };
</script></body></html>
"""


class Server:
    def __init__(self, root=ROOT, extra=None):
        self.root = root
        self.extra = extra or {}
        handler_extra = self.extra

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=root, **kw)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path in handler_extra:
                    body, mime = handler_extra[path]
                    if isinstance(body, str):
                        body = body.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()

            def log_message(self, *a):
                pass

        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


def render(src, out_prefix, views=("iso", "front", "top"), size=(900, 700),
           anim=None, zoom=1.0, axes=True, page=PAGE):
    mounts = {"/__render.html": (page, "text/html")}
    if src.startswith("http"):
        src_url = src
    else:
        with open(src, "rb") as fh:
            mounts["/__model.glb"] = (fh.read(), "model/gltf-binary")
        src_url = "/__model.glb"
    server = Server(extra=mounts)
    outputs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME,
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page_obj = browser.new_page(viewport={"width": size[0], "height": size[1]})
        errors = []
        page_obj.on("pageerror", lambda e: errors.append(str(e)))
        page_obj.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page_obj.goto(f"http://127.0.0.1:{server.port}/__render.html"
                      f"?src={src_url}&w={size[0]}&h={size[1]}")
        try:
            page_obj.wait_for_function("window.state && (window.state.ready || window.state.error)",
                                       timeout=180000)
        except Exception:
            print("load timeout; console:", errors[:10])
            raise
        if page_obj.evaluate("window.state.error"):
            raise RuntimeError("GLTF load failed: " + page_obj.evaluate("window.state.error"))
        info = page_obj.evaluate("window.state.info")
        page_obj.evaluate(f"window.showAxes({str(axes).lower()})")

        for view in views:
            if anim:
                name, t = anim
                page_obj.evaluate(f"window.playAt({json.dumps(name)}, {t})")
            page_obj.evaluate(f"window.setView('{view}', {zoom})")
            page_obj.evaluate("window.draw()")
            out = f"{out_prefix}_{view}.png"
            page_obj.locator("canvas").screenshot(path=out)
            outputs.append(out)
        browser.close()
    server.stop()
    if errors:
        print("page errors:", errors[:5])
    return info, outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("out_prefix")
    parser.add_argument("--views", default="iso,front,top")
    parser.add_argument("--anim", default=None, help="Name@time")
    parser.add_argument("--strip", default=None,
                        help="Name@t0,t1,... renders one view per time into a filmstrip")
    parser.add_argument("--zoom", type=float, default=1.0)
    parser.add_argument("--size", default="900x700")
    parser.add_argument("--no-axes", action="store_true")
    args = parser.parse_args()

    if args.strip:
        name, _, times = args.strip.partition("@")
        outs = []
        for t in times.split(","):
            width, height = (int(v) for v in args.size.split("x"))
            _, o = render(args.src, f"{args.out_prefix}_t{t}", args.views.split(","),
                          (width, height), (name, float(t)), args.zoom, not args.no_axes)
            outs += o
        print("\n".join(outs))
        raise SystemExit(0)

    anim = None
    if args.anim:
        name, _, t = args.anim.partition("@")
        anim = (name, float(t or 0))
    width, height = (int(v) for v in args.size.split("x"))
    info, outs = render(args.src, args.out_prefix, args.views.split(","), (width, height),
                        anim, args.zoom, not args.no_axes)
    print(json.dumps(info, indent=1)[:2000])
    print("\n".join(outs))
