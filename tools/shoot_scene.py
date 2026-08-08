"""Screenshot the web demo itself, so the assembled scene can be checked."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from render import CHROME, ROOT, Server


def shoot(out, camera="wide", size=(1280, 800), settle=2500, script=None):
    server = Server()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME,
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"http://127.0.0.1:{server.port}/web/index.html")
        page.wait_for_function("!document.getElementById('loading')", timeout=240000)
        page.evaluate(f"document.getElementById('cam-{camera}').click()")
        if script:
            page.evaluate(script)
        page.wait_for_timeout(settle)
        page.screenshot(path=out)
        browser.close()
    server.stop()
    if errors:
        print("page errors:", errors[:5])
    print(out)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--camera", default="wide")
    parser.add_argument("--size", default="1280x800")
    parser.add_argument("--settle", type=int, default=2500)
    parser.add_argument("--script", default=None)
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.split("x"))
    shoot(args.out, args.camera, (width, height), args.settle, args.script)
