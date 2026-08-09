"""Boot the game in headless Chromium, run the simulation, screenshot it.

The renderer is software here, so real time crawls; the harness drives the
battle by stepping the simulation directly instead of waiting for frames.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from render import CHROME, Server


def playtest(out="renders/game.png", size=(1400, 860), script=None, sim_seconds=0.0,
             camera=None, verbose=True, autoplay=False):
    server = Server()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME,
                                     args=["--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader", "--no-sandbox"])
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        messages = []
        page.on("pageerror", lambda e: messages.append("PAGEERROR: " + str(e)))
        page.on("console", lambda m: messages.append(f"{m.type}: {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("requestfailed", lambda r: messages.append(f"REQFAIL: {r.url}"))

        page.goto(f"http://127.0.0.1:{server.port}/web/play.html")
        try:
            page.wait_for_function("window.game !== undefined", timeout=300000)
        except Exception:
            print("boot failed. messages:")
            print("\n".join(messages[:20]))
            print("loading text:", page.evaluate(
                "document.getElementById('loading') && document.getElementById('loading').textContent"))
            browser.close()
            server.stop()
            raise

        if sim_seconds:
            # Step the battle in fixed slices without waiting for real frames.
            # `autoplay` gives the blue side a bot too, so both sides push.
            page.evaluate("""({seconds, autoplay}) => {
                const g = window.game;
                const blue = autoplay
                    ? new g.Bot(g.battle, [...g.playable].sort(() => Math.random() - 0.5), 'blue', 1)
                    : null;
                const step = 1 / 30;
                for (let t = 0; t < seconds; t += step) {
                    g.battle.update(step);
                    g.bot.update(step);
                    if (blue) blue.update(step);
                }
            }""", {"seconds": sim_seconds, "autoplay": autoplay})

        if camera:
            page.evaluate(f"window.game.rig.setView('{camera}')")
        if script:
            page.evaluate(script)

        page.wait_for_timeout(2500)
        page.screenshot(path=out)

        state = page.evaluate("""() => ({
            time: window.game.battle.time,
            over: window.game.battle.over,
            units: window.game.battle.units.length,
            crowns: window.game.battle.crowns,
            elixir: window.game.battle.elixir,
            towers: window.game.battle.towers.map(t => [t.id, Math.round(t.hp)]),
            types: window.game.battle.units.map(u => u.type + ':' + u.team + ':' + u.state),
        })""")
        browser.close()
    server.stop()
    if verbose:
        errors = [m for m in messages if m.startswith(("PAGEERROR", "error", "REQFAIL"))]
        if errors:
            print("PAGE ISSUES:")
            print("\n".join(dict.fromkeys(errors))[:3000])
        print("state:", state)
        print(out)
    return state, messages


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="renders/game.png")
    parser.add_argument("--sim", type=float, default=0.0)
    parser.add_argument("--camera", default=None)
    parser.add_argument("--autoplay", action="store_true")
    parser.add_argument("--script", default=None)
    parser.add_argument("--size", default="1400x860")
    args = parser.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    playtest(args.out, (w, h), args.script, args.sim, args.camera, autoplay=args.autoplay)
