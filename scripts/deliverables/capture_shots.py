# -*- coding: utf-8 -*-
"""Capture a screenshot of every NAV section of the app.

Reusable across releases: it auto-discovers sections from the app's own NAV array,
so new sections are picked up automatically. Output matches the deliverable style
(2160x1215, 16:9) used by the docx / pptx generators.

Usage:
    python scripts/deliverables/capture_shots.py [out_dir] [--only id1,id2]

Defaults: out_dir = <repo>/build/shots . The app is loaded from frontend/index.html
via file:// (no server needed). Requires: playwright (chromium), pillow.
"""
import sys, pathlib, argparse
from playwright.sync_api import sync_playwright
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stream_demo import DEMO_JS  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
APP = (REPO / "frontend" / "index.html").as_uri()
STREAM_VIEWS = {"org", "stream", "features", "streampi", "roam", "sos", "sysdemo"}   # заполняются асинхронно


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?", default=str(REPO / "build" / "shots"))
    ap.add_argument("--only", default="", help="comma-separated section ids to limit capture")
    args = ap.parse_args()
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    only = [s.strip() for s in args.only.split(",") if s.strip()]

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1080, "height": 608}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(APP)
        pg.wait_for_function("() => typeof activate === 'function' && typeof NAV !== 'undefined'")
        pg.wait_for_timeout(400)
        pg.evaluate(DEMO_JS)                     # демо-оргструктура: 2 стрима, 7 команд, данные стрима
        pg.wait_for_timeout(300)
        sections = pg.evaluate("()=>NAV.flatMap(g=>g.items.map(i=>i[0]))")
        if only:
            sections = [s for s in sections if s in only]
        done = 0
        for sid in sections:
            pg.evaluate("(id)=>activate(id)", sid)
            pg.evaluate("()=>window.scrollTo(0,0)")
            pg.wait_for_timeout(1100 if sid in STREAM_VIEWS else 450)
            raw = out / (sid + "_raw.png")
            pg.screenshot(path=str(raw))
            im = Image.open(raw).convert("RGB")
            if im.size != (2160, 1215):
                im = im.resize((2160, 1215))
            im.save(out / (sid + ".jpg"), quality=88)
            for _ in range(20):                  # файл может держать синхронизация (Dropbox) — повторяем
                try: raw.unlink(); break
                except PermissionError: pg.wait_for_timeout(250)
            done += 1
            print("captured", sid)
        ctx.close(); b.close()
    print("done:", done, "sections ->", out)


if __name__ == "__main__":
    main()
