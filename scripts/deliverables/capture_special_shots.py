# -*- coding: utf-8 -*-
"""Специальные кадры для документов и презентации (1440×810 @1.5 → 2160×1215, build/shots/<имя>.jpg):
окно входа, режим администратора, помощник, фрагменты разделов (распределения в аналитике, диаграмма Исикавы,
форматы ретро), релизная доска и «Состав релизов» на Kanban, окно отчёта по спринту.
Кадры доски — capture_board_shots.py, уровень стрима — capture_stream_shots.py.
Запуск: python scripts/deliverables/capture_special_shots.py [имя ...]"""
import sys, pathlib
from playwright.sync_api import sync_playwright
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from stream_demo import DEMO_JS  # noqa: E402  шапка «Стрим › Команда» как в остальных снимках

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "shots"; OUT.mkdir(parents=True, exist_ok=True)
APP = (ROOT / "frontend" / "index.html").as_uri()


def scroll_to_text(view, text, dy=-80):
    """Активировать раздел и прокрутить к самому вложенному элементу с данным текстом."""
    return ("()=>{activate(%r);const all=[...document.querySelectorAll('#v_%s *')].filter(e=>e.children.length<3&&e.textContent.includes(%r));"
            "const e=all[all.length-1]||null;if(e){e.scrollIntoView({block:'start'});window.scrollBy(0,%d);}else window.scrollTo(0,0);}") % (view, view, text, dy)


SHOTS = {
 "usermgmt": ["()=>{setPerm('admin');applyPerms();updateRoleBtn();activate('dash');window.scrollTo(0,0);}"],
 "login": ["()=>{activate('dash');window.scrollTo(0,0);openLogin();}"],
 "chat": ["()=>{activate('dash');window.scrollTo(0,0);document.getElementById('chatfab').click();}"],
 "analytics_dist": [scroll_to_text("analytics", "Распределение объёма по типам")],
 "risks_ishikawa": [scroll_to_text("risks", "Диаграмма Исикавы", -60)],
 "retro_mood": [scroll_to_text("retro", "Форматы ретроспектив", -260)],
 "kanban_release": ["()=>{UI.kanBoard='b-release';views();activate('kanban');window.scrollTo(0,0);}"],
 "kanban_compose": ["()=>{UI.kanBoard='b-release-compose';views();activate('kanban');window.scrollTo(0,0);}"],
 "report": ["()=>{activate('dash');window.scrollTo(0,0);const C=compute();const n=(typeof doneSprintForReport==='function'&&doneSprintForReport(C))||C.cur;openPptxModalFor(n);}"],
 # эргономика v2.6: «Мой день», вкладки хаба и компактное меню, меню «＋ Создать» и пользователя, первые шаги, мастер стрима
 "s_myday": ["()=>{lsSetS('me:t1',ST.team[0].name);views();activate('myday');window.scrollTo(0,0);}"],
 "s_hubs": ["()=>{activate('wsjf');window.scrollTo(0,0);}"],
 "s_menus": ["()=>{activate('dash');window.scrollTo(0,0);}", "()=>{document.getElementById('qcbtn').click();}"],
 "s_umenu": ["()=>{activate('dash');window.scrollTo(0,0);}", "()=>{document.getElementById('ubtn').click();}"],
 "s_onb": ["async()=>{const id=await orgAddTeam('Новая команда','s1','empty');await switchTeam(id);views();activate('dash');window.scrollTo(0,0);}"],
 "s_wizard": ["()=>{activate('org');window.scrollTo(0,0);wizOpen();}"],
 # «Мой профиль» (v2.8): серверный сеанс на подменённых ответах — логин, привязка, должность в стриме, смена пароля
 "s_profile": ["MOCK", "async()=>{AUTH.username='lead';AUTH.user='Петрова Мария';AUTH.role='EDITOR';AUTH.member='Петрова М.';setPerm('editor');applyPerms();updateRoleBtn();"
               "ST.board.items=ST.board.items||[];ST.board.items.push({id:'pf1',t:'sticky',x:0,y:0,w:100,h:80,text:'Ретро',comments:[{id:'c1',a:'Иванов А.',"
               "t:'@Петрова М. проверь, пожалуйста, макет корзины',ts:'2026-09-09T10:00:00Z',m:['Петрова М.']}]});views();activate('profile');window.scrollTo(0,0);}"],
 "s_profile2": ["MOCK", "async()=>{AUTH.username='lead';AUTH.user='Петрова Мария';AUTH.role='EDITOR';AUTH.member='Петрова М.';setPerm('editor');applyPerms();updateRoleBtn();"
                "views();activate('profile');await new Promise(r=>setTimeout(r,500));const c=document.getElementById('pf_stream');if(c){c.scrollIntoView({block:'start'});window.scrollBy(0,-120);}}"],
 # серверные окна администратора — на подменённых ответах сервера (демо-учётки, без реальных данных)
 "admin_users": ["MOCK", "async()=>{activate('dash');window.scrollTo(0,0);await openUsers();}"],
 "admin_audit": ["MOCK", "async()=>{views();activate('audit');await new Promise(r=>setTimeout(r,600));"
                 "const t=[...document.querySelectorAll('#v_audit .ctitle')].pop();if(t){t.scrollIntoView({block:'start'});window.scrollBy(0,-90);}}"],
}
MOCK = r"""()=>{AUTH.mode='server';AUTH.token='demo';AUTH.username='admin';AUTH.user='Администратор';AUTH.role='ADMIN';setPerm('admin');applyPerms();updateRoleBtn();
 const U=[{username:'admin',name:'Администратор',role:'ADMIN',active:true},{username:'lead',name:'Петрова М. (лидер стрима)',role:'EDITOR',active:true},
  {username:'po.pay',name:'Орлов Д.',role:'EDITOR',active:true},{username:'dev.search',name:'Смирнов К.',role:'EDITOR',active:true},{username:'viewer',name:'Наблюдатель',role:'VIEWER',active:true}];
 const now=Date.parse('2026-09-10T10:42:00Z'),E=[['AUTH','login','lead','POST','/api/auth/login',200,'Вход выполнен'],
  ['DATA','state_saved','lead','PUT','/api/state',200,'Сохранение данных, версия 57 (команда t1)'],['CLIENT','switch_team','lead','UI','',null,'t4'],
  ['ACCESS','PUT','lead','PUT','/api/org/streams/s1/doc',200,null],['ACCESS','POST','admin','POST','/api/org/teams',200,null],
  ['ACCESS','POST','admin','POST','/api/org/memberships',200,null],['DENY','PUT','viewer','PUT','/api/state',403,null],
  ['DATA','state_saved','dev.search','PUT','/api/state',200,'Сохранение данных, версия 12 (команда t4)'],['CLIENT','import_team','admin','UI','',null,'streams_data.json']]
  .map((e,i)=>({ts:now-i*137000,category:e[0],action:e[1],username:e[2],method:e[3],path:e[4],status:e[5],detail:e[6]}));
 const orig=window.fetch;window.fetch=(u,o)=>{const s=String(u);const J=x=>Promise.resolve(new Response(JSON.stringify(x),{status:200,headers:{'Content-Type':'application/json'}}));
  if(s.includes('api/auth/users'))return J(U);if(s.includes('api/audit'))return J({enabled:true,total:E.length,events:E});return orig(u,o);};}"""
RESET = ("()=>{['loginmodal','accmodal','usersmodal'].forEach(id=>{const m=document.getElementById(id);if(m)m.classList.remove('open');});"
         "document.querySelectorAll('.modal.open,.pptx-modal.open').forEach(m=>m.classList.remove('open'));"
         "const cp=document.getElementById('chatpanel');if(cp&&cp.classList.contains('open'))document.getElementById('chatfab').click();"
         "const t=document.getElementById('toast');if(t)t.classList.remove('show');}")

want = sys.argv[1:] or list(SHOTS)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name in want:
        ctx = b.new_context(viewport={"width": 1440, "height": 810}, device_scale_factor=1.5)
        pg = ctx.new_page(); pg.goto(APP)
        pg.wait_for_function("()=>typeof activate==='function'&&typeof ORG!=='undefined'"); pg.wait_for_timeout(400)
        pg.evaluate(DEMO_JS); pg.evaluate(RESET); pg.wait_for_timeout(300)
        for js in SHOTS[name]: pg.evaluate(MOCK if js == "MOCK" else js)
        pg.wait_for_timeout(1000)
        pg.evaluate("()=>{const t=document.getElementById('toast');if(t)t.classList.remove('show');}")
        raw = OUT / (name + "_raw.png"); pg.screenshot(path=str(raw))
        im = Image.open(raw).convert("RGB"); im = im.resize((2160, 1215)) if im.size != (2160, 1215) else im
        im.save(OUT / (name + ".jpg"), quality=88)
        for _ in range(20):
            try: raw.unlink(); break
            except PermissionError: pg.wait_for_timeout(250)
        ctx.close(); print("captured", name + ".jpg")
    b.close()
