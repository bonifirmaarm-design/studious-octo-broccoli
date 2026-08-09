"""Contact sheet of one pose per clip for every built unit, in a single browser."""

import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render import CHROME, PAGE, Server
from roster import ROSTER

TILE = (300, 340)
# clip name -> time to park on
POSES = [("Idle", 0.0), ("Walk", 0.2), ("Attack", 0.40), ("Shoot", 0.52),
         ("Jump", 0.84), ("Smash", 0.50), ("Die", 0.66), ("Hit", 0.10)]


def main(units=None, out="renders/pose_sheet.png", view="iso"):
    units = units or list(ROSTER)
    mounts = {"/__render.html": (PAGE, "text/html")}
    for key in units:
        path = f"web/assets/units/{key}.glb"
        with open(path, "rb") as fh:
            mounts[f"/{key}.glb"] = (fh.read(), "model/gltf-binary")
    server = Server(extra=mounts)

    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME,
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page = browser.new_page(viewport={"width": TILE[0], "height": TILE[1]})
        for key in units:
            page.goto(f"http://127.0.0.1:{server.port}/__render.html"
                      f"?src=/{key}.glb&w={TILE[0]}&h={TILE[1]}")
            page.wait_for_function("window.state && (window.state.ready || window.state.error)",
                                   timeout=120000)
            page.evaluate("window.showAxes(false)")
            available = {name for name, _ in page.evaluate("window.state.info.animations")}
            tiles = []
            for clip, t in POSES:
                if clip not in available:
                    continue
                page.evaluate(f"window.playAt('{clip}', {t})")
                page.evaluate(f"window.setView('{view}', 1.0)")
                page.evaluate("window.draw()")
                shot = f"renders/_p_{key}_{clip}.png"
                page.locator("canvas").screenshot(path=shot)
                tiles.append(shot)
            rows.append((key, tiles))
            print("posed", key, len(tiles))
        browser.close()
    server.stop()

    columns = max(len(t) for _, t in rows)
    sheet = Image.new("RGB", (TILE[0] * columns, TILE[1] * len(rows)), (22, 26, 36))
    for r, (key, tiles) in enumerate(rows):
        for c, shot in enumerate(tiles):
            sheet.paste(Image.open(shot), (TILE[0] * c, TILE[1] * r))
    sheet.save(out)
    for r, (key, tiles) in enumerate(rows):
        print(f"row {r}: {key}  ({len(tiles)} poses)")
    print(out, sheet.size)


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args or None)
