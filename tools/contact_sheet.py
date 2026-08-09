"""Render every raw scan in assets_raw/ into one contact sheet, in a single browser.

Used to work out which uploaded archive is which card.
"""

import os
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import objmesh
from glb import GLB, compute_normals
from render import CHROME, PAGE, Server

TILE = (360, 420)


def static_glb(src, out):
    positions, uvs, faces = objmesh.load_obj(os.path.join(src, "output.obj"))
    positions, uvs, indices = objmesh.unify(positions, uvs, faces)
    lo, hi = positions.min(0), positions.max(0)
    centre = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    positions = (positions - centre) / (hi[1] - lo[1])

    glb = GLB()
    texture = glb.add_texture(glb.add_image(os.path.join(src, "textured_mesh.jpg")))
    material = glb.add_material("m", base_color_texture=texture, roughness=0.8)
    mesh = glb.add_mesh("m", positions.astype(np.float32), indices,
                        normals=compute_normals(positions, indices), uvs=uvs, material=material)
    glb.add_node("model", mesh=mesh, root=True)
    glb.save(out)
    return out


def main(out_sheet="renders/contact_sheet.png", views=("front", "left")):
    sources = sorted(d for d in os.listdir("assets_raw")
                     if os.path.exists(f"assets_raw/{d}/output.obj"))
    scratch = os.environ.get("SCRATCH", "/tmp")
    mounts = {"/__render.html": (PAGE, "text/html")}
    for name in sources:
        path = static_glb(f"assets_raw/{name}", f"{scratch}/{name}.glb")
        with open(path, "rb") as fh:
            mounts[f"/{name}.glb"] = (fh.read(), "model/gltf-binary")
    server = Server(extra=mounts)

    tiles = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME,
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page = browser.new_page(viewport={"width": TILE[0], "height": TILE[1]})
        for name in sources:
            page.goto(f"http://127.0.0.1:{server.port}/__render.html"
                      f"?src=/{name}.glb&w={TILE[0]}&h={TILE[1]}")
            page.wait_for_function("window.state && (window.state.ready || window.state.error)",
                                   timeout=120000)
            page.evaluate("window.showAxes(false)")
            for view in views:
                page.evaluate(f"window.setView('{view}', 1.0)")
                page.evaluate("window.draw()")
                shot = f"renders/_tile_{name}_{view}.png"
                page.locator("canvas").screenshot(path=shot)
                tiles.append((name, view, shot))
            print("rendered", name)
        browser.close()
    server.stop()

    per_row = len(views)
    rows = len(sources)
    sheet = Image.new("RGB", (TILE[0] * per_row, TILE[1] * rows), (22, 26, 36))
    for i, (name, view, shot) in enumerate(tiles):
        sheet.paste(Image.open(shot), (TILE[0] * (i % per_row), TILE[1] * (i // per_row)))
    sheet.save(out_sheet)
    for i, name in enumerate(sources):
        print(f"row {i}: {name}")
    print(out_sheet, sheet.size)


if __name__ == "__main__":
    main(*sys.argv[1:])
