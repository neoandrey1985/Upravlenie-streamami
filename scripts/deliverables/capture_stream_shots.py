# -*- coding: utf-8 -*-
"""Скриншоты уровня стрима и оргструктуры для презентации и иллюстрированного описания
(1440×810 @1.5 → 2160×1215, build/shots/s_*.jpg) на демо-оргструктуре из stream_demo.DEMO_JS:
  s_org.jpg        — раздел «Стримы и команды» (2 стрима, 7 команд);
  s_switch.jpg     — переключатель «Стрим › Команда» в шапке (раскрыт);
  s_stream.jpg     — обзор стрима: KPI и таблица команд;
  s_charts.jpg     — обзор стрима: burn-up PI и velocity команд по итерациям;
  s_features.jpg   — фичи стрима (таблица с WSJF и прогрессом);
  s_kanban.jpg     — канбан фич по статусам;
  s_pi.jpg         — программная доска PI и цели команд;
  s_deps.jpg       — межкомандные зависимости с конфликтами;
  s_roam.jpg       — риски ROAM;
  s_sos.jpg        — Scrum of Scrums;
  s_demo.jpg       — System Demo.
Запуск: python scripts/deliverables/capture_stream_shots.py [имя ...]"""
import sys, pathlib
from playwright.sync_api import sync_playwright
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stream_demo import DEMO_JS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "shots"; OUT.mkdir(parents=True, exist_ok=True)
APP = (ROOT / "frontend" / "index.html").as_uri()


def to(sel, dy=-90):
    return "async()=>{await new Promise(r=>setTimeout(r,900));const e=document.querySelector(%r);if(e){e.scrollIntoView({block:'start'});window.scrollBy(0,%d);}}" % (sel, dy)


SHOTS = {
 "s_org": ["()=>{activate('org');window.scrollTo(0,0);}"],
 "s_switch": ["()=>{activate('stream');window.scrollTo(0,0);}", "async()=>{await new Promise(r=>setTimeout(r,900));document.getElementById('teamsw').click();}"],
 "s_stream": ["()=>{activate('stream');}", to("#str_stream .grid.kpis", -150)],
 "s_charts": ["()=>{activate('stream');}", to("#str_stream .str-charts", -110)],
 "s_features": ["()=>{try{localStorage.setItem('str_fview','table');}catch(e){}activate('features');streamRerender();window.scrollTo(0,0);}"],
 "s_kanban": ["()=>{try{localStorage.setItem('str_fview','kanban');}catch(e){}activate('features');streamRerender();window.scrollTo(0,0);}"],
 "s_pi": ["()=>{activate('streampi');window.scrollTo(0,0);}"],
 "s_deps": ["()=>{activate('streampi');}", to("#str_streampi .card:last-child", -60)],
 "s_roam": ["()=>{activate('roam');window.scrollTo(0,0);}"],
 "s_sos": ["()=>{activate('sos');window.scrollTo(0,0);}"],
 "s_demo": ["()=>{activate('sysdemo');window.scrollTo(0,0);}"],
}
CLEAN = "()=>{const t=document.getElementById('toast');if(t)t.classList.remove('show');}"

want = sys.argv[1:] or list(SHOTS)
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 810}, device_scale_factor=1.5)
    pg = ctx.new_page(); pg.goto(APP)
    pg.wait_for_function("()=>typeof activate==='function'&&typeof ORG!=='undefined'"); pg.wait_for_timeout(400)
    pg.evaluate(DEMO_JS); pg.wait_for_timeout(500)
    for name in want:
        pg.evaluate("()=>{const d=document.getElementById('teamdm');if(d)d.classList.remove('open');}")
        for js in SHOTS[name]: pg.evaluate(js)
        pg.wait_for_timeout(1000); pg.evaluate(CLEAN); pg.wait_for_timeout(200)
        raw = OUT / (name + "_raw.png"); pg.screenshot(path=str(raw))
        im = Image.open(raw).convert("RGB"); im = im.resize((2160, 1215)) if im.size != (2160, 1215) else im
        im.save(OUT / (name + ".jpg"), quality=88)
        for _ in range(20):
            try: raw.unlink(); break
            except PermissionError: pg.wait_for_timeout(250)
        print("captured", name + ".jpg")
    pg.evaluate("()=>{try{localStorage.setItem('str_fview','table');}catch(e){}}")
    ctx.close(); b.close()
