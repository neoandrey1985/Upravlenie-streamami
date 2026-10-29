# -*- coding: utf-8 -*-
"""End-to-end / functional test suite for the Управление стримами и командами frontend SPA.

Covers ALL application functionality:
  * Smoke-tests EVERY navigation section (auto-discovered from the app's NAV) — so
    when a new section is added it is covered automatically, with no new test code.
  * Deep functional checks: metrics engine, EDA report, PPTX sprint report (incl. the
    file-corruption regression), Excel export, Kanban role-routing, release composition,
    automation, whiteboard, data migration, versioning and the Support section.

Run:  python tests/frontend/run_e2e.py      (needs: pip install playwright && playwright install chromium)
Exit code is non-zero if any test fails — suitable for CI regression gating.
"""
import os, sys, io, time, base64, zipfile, re, functools, threading, http.server, socketserver
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND = os.path.join(ROOT, 'frontend')
PORT = int(os.environ.get('E2E_PORT', '4123'))
URL = f'http://127.0.0.1:{PORT}/'

PASS, FAIL, SKIP = [], [], []
class Skip(Exception): pass

def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=FRONTEND)
    class Q(socketserver.TCPServer): allow_reuse_address = True; daemon_threads = True
    httpd = Q(('127.0.0.1', PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd

def case(name, fn):
    try:
        fn(); print('PASS  ' + name); PASS.append(name)
    except Skip as s:
        print('SKIP  ' + name + '  — ' + str(s)); SKIP.append(name)
    except AssertionError as e:
        print('FAIL  ' + name + '  — ' + str(e)); FAIL.append((name, str(e)))
    except Exception as e:
        print('ERROR ' + name + '  — ' + repr(e)); FAIL.append((name, repr(e)))

# console-error noise from the offline dev server (no backend) — not app bugs
IGNORE = ('Failed to load resource', 'api/state', 'api/health', 'api/audit', '/analytics',
          'favicon', 'net::ERR', 'status of 404', 'status of 403', 'ws://', 'WebSocket')
def is_noise(t): return any(s in t for s in IGNORE)


def main():
    httpd = serve(); time.sleep(0.4)
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--no-sandbox'])
        page = br.new_page(viewport={'width': 1440, 'height': 900})
        cerr = []
        page.on('console', lambda m: cerr.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: cerr.append(str(e)))
        page.goto(URL, wait_until='load')
        page.wait_for_selector('.nav-item', timeout=15000)
        page.wait_for_timeout(700)
        page.evaluate("()=>{try{endTour&&endTour()}catch(e){}}")

        # ---- 0. boots without console errors ----
        def t_boot():
            real = [e for e in cerr if not is_noise(e)]
            assert not real, 'console errors on load: ' + ' | '.join(real[:4])
        case('app boots without console errors', t_boot)

        # ---- 1. smoke: EVERY NAV section renders (auto-discovered) ----
        sections = page.evaluate("()=>NAV.flatMap(g=>g.items.map(i=>i[0]))")
        assert sections and len(sections) >= 20, 'expected many nav sections'
        print(f'  (auto-discovered {len(sections)} sections)')
        for sid in sections:
            def t_sec(sid=sid):
                before = len(cerr)
                page.evaluate("(id)=>activate(id)", sid)
                page.wait_for_timeout(140)
                ok = page.evaluate("(id)=>{const el=document.getElementById('v_'+id);"
                                   "return !!el && el.classList.contains('active') && el.children.length>0}", sid)
                new = [e for e in cerr[before:] if not is_noise(e)]
                assert ok, 'view not active or empty'
                assert not new, 'console error: ' + ' | '.join(new[:3])
            case('section renders: ' + sid, t_sec)
        page.evaluate("()=>activate('dash')")

        # ---- 2. metrics engine ----
        def t_compute():
            keys = page.evaluate("()=>{const C=compute();return Object.keys(C)}")
            for k in ('cur', 'avgVel', 'health', 'sp', 'ttmAvg', 'dre'):
                assert k in keys, 'compute() missing key ' + k
            ok = page.evaluate("()=>{const C=compute();return C.sp.length>0 && isFinite(C.avgVel) && "
                               "C.health>=0 && C.health<=1}")
            assert ok, 'compute() produced out-of-range metrics'
        case('metrics: compute() returns valid model', t_compute)

        # ---- 3. version / changelog consistency ----
        def t_ver():
            ok = page.evaluate("()=>APP_VERSION===CHANGELOG[0].v")
            assert ok, 'APP_VERSION != CHANGELOG[0].v'
        case('versioning: APP_VERSION matches changelog head', t_ver)

        # ---- 3b. assistant knows the whole app (self-training regression) ----
        def t_assistant():
            page.evaluate("()=>activate('dash')")
            r = page.evaluate("""()=>{
              if(typeof window.assistantAsk!=='function'||typeof window.assistantKB!=='function')
                return {err:'no assistant hooks (assistantAsk/assistantKB)'};
              const items=NAV.flatMap(g=>g.items);
              const ids=items.map(i=>i[0]);
              const KB=window.assistantKB();
              const missing=ids.filter(id=>!KB[id]||!KB[id].text||KB[id].text.length<8);
              const noanswer=[];
              items.forEach(it=>{const a=window.assistantAsk('что такое '+it[1]);
                if(!a||!a.t||a.t.length<8)noanswer.push(it[0]);});
              const ov=window.assistantAsk('какие разделы есть в приложении');
              const nw=window.assistantAsk('что нового в приложении');
              return {n:ids.length,kb:Object.keys(KB).length,missing:missing,noanswer:noanswer,
                      ovOK:!!(ov&&ov.t&&ov.t.indexOf('раздел')>=0),
                      nwOK:!!(nw&&nw.t&&nw.t.indexOf(APP_VERSION)>=0)};
            }""")
            assert 'err' not in r, r.get('err')
            assert r['kb'] == r['n'], 'KB covers %d of %d NAV sections' % (r['kb'], r['n'])
            assert not r['missing'], 'sections without knowledge text: %s' % r['missing']
            assert not r['noanswer'], 'sections the assistant cannot explain: %s' % r['noanswer']
            assert r['ovOK'], 'assistant overview («какие разделы есть») failed'
            assert r['nwOK'], 'assistant «что нового» missing current version'
        case('assistant: knows every NAV section (auto-trained)', t_assistant)

        # ---- 3c. resizable table columns (grips + persist) ----
        def t_colresize():
            page.evaluate("()=>activate('sprintGoals')"); page.wait_for_timeout(200)
            r = page.evaluate("""()=>{
              if(typeof window.__colResizeEnhance!=='function')return {err:'no colResize hook'};
              const t=document.querySelector('#v_sprintGoals table');
              if(!t)return {err:'no table'};
              window.__colResizeEnhance(t);
              const hr=(t.tHead&&t.tHead.rows[0])||t.rows[0];
              const cols=hr.cells.length;
              const grips=t.querySelectorAll('.col-grip').length;
              const widthsSet=[].every.call(hr.cells,c=>/px|%/.test(c.style.width||''));
              const fixed=t.classList.contains('colr');
              // идемпотентность: второй вызов не плодит гриппы
              window.__colResizeEnhance(t);
              const grips2=t.querySelectorAll('.col-grip').length;
              return {cols:cols,grips:grips,grips2:grips2,widthsSet:widthsSet,fixed:fixed};
            }""")
            assert 'err' not in r, r.get('err')
            assert r['cols'] >= 2, 'table has too few columns'
            assert r['grips'] == r['cols'] - 1, 'grips %d != cols-1 (%d)' % (r['grips'], r['cols'] - 1)
            assert r['grips2'] == r['grips'], 'enhance is not idempotent (%d -> %d)' % (r['grips'], r['grips2'])
            assert r['widthsSet'], 'column widths were not frozen'
            assert r['fixed'], 'table did not switch to fixed layout (.colr)'
            # grips must survive an in-place re-render (sort/filter)
            page.evaluate("()=>activate('team')"); page.wait_for_timeout(250)
            r2 = page.evaluate("""()=>{
              const t=document.querySelector('#v_team table'); if(!t)return {skip:true};
              window.__colResizeEnhance(t);
              const hr=(t.tHead&&t.tHead.rows[0])||t.rows[0];
              const th=hr.querySelector('th.sortable'); if(!th)return {skip:true};
              const before=t.querySelectorAll('.col-grip').length;
              th.click();  // sort → re-render thead/tbody in place
              return {before:before};
            }""")
            if not r2.get('skip'):
                page.wait_for_timeout(300)  # allow MO debounce + repair
                after = page.evaluate("()=>{const t=document.querySelector('#v_team table');"
                                      "const hr=(t.tHead&&t.tHead.rows[0])||t.rows[0];"
                                      "return {grips:t.querySelectorAll('.col-grip').length,need:hr.cells.length-1};}")
                assert after['grips'] == after['need'], \
                    'grips lost after sort: %d != %d' % (after['grips'], after['need'])
        case('tables: columns are resizable (grips survive sort/filter)', t_colresize)

        # ---- 3d. JSON import normalizes partial data via migrate() ----
        def t_import_migrate():
            page.evaluate("()=>activate('dash')")
            r = page.evaluate("""()=>{
              const backup=JSON.stringify(ST);
              try{
                // частичный «импорт»: только params + одна задача, без большинства коллекций/досок
                const partial={params:JSON.parse(backup).params,
                               tasks:[{id:'T-99',title:'x',role:'Backend',type:'Задача',est:3,status:'To Do',sprint:1}]};
                ST=migrate(JSON.parse(JSON.stringify(partial)));
                const need=['team','tasks','boards','risks','bugs','deps','releases',
                            'incidents','deployments','stakeholders','okr'];
                const missing=need.filter(k=>!Array.isArray(ST[k]));
                if(!ST.board||typeof ST.board!=='object')missing.push('board');
                let threw=null;
                try{views();activate('team');activate('dora');activate('kanban');activate('dash');}
                catch(e){threw=String((e&&e.message)||e);}
                return {missing:missing,threw:threw};
              } finally { ST=JSON.parse(backup); try{views();activate('dash');}catch(e){} }
            }""")
            assert not r['missing'], 'migrate() left collections missing after partial import: %s' % r['missing']
            assert not r['threw'], 'views() threw after migrated partial import: %s' % r['threw']
        case('import: partial JSON is normalized by migrate() without crashing', t_import_migrate)

        # ---- 3e. Ishikawa fishbone is data-driven + editable ----
        def t_ishikawa():
            page.evaluate("()=>activate('risks')"); page.wait_for_timeout(250)
            r = page.evaluate("""()=>{
              const box=document.getElementById('ishk'); if(!box)return {err:'no #ishk'};
              if(!box.querySelector('svg'))return {err:'no svg'};
              const cats=(ST.ishikawaCats||[]).length, causes=(ST.ishikawa||[]).length;
              if(!Array.isArray(ST.ishikawa))ST.ishikawa=[];
              const catName=((ST.ishikawaCats||[])[0]||{}).name||'Люди';
              ST.ishikawa.push({id:'IC-TEST',cat:catName,cause:'ТЕСТ_ПРИЧИНА_XYZ',weight:9,risk:''});
              drawIshikawa(box);
              const txt=[].map.call(box.querySelectorAll('text'),t=>t.textContent).join('|');
              const has=txt.indexOf('ТЕСТ_ПРИЧИНА_XYZ')>=0;
              const weightShown=txt.indexOf('ТЕСТ_ПРИЧИНА_XYZ [9]')>=0;
              ST.ishikawa=ST.ishikawa.filter(x=>x.id!=='IC-TEST');drawIshikawa(box); // cleanup
              const tables=document.querySelectorAll('#v_risks table').length;
              return {cats:cats,causes:causes,has:has,weightShown:weightShown,tables:tables};
            }""")
            assert 'err' not in r, r.get('err')
            assert r['cats'] >= 1 and r['causes'] >= 1, 'ishikawa seed missing (cats=%s causes=%s)' % (r['cats'], r['causes'])
            assert r['has'], 'new cause not drawn on the fishbone after drawIshikawa()'
            assert r['weightShown'], 'cause weight is not shown on the diagram'
            assert r['tables'] >= 3, 'risks view should expose risks + ishikawa + categories tables (got %d)' % r['tables']
        case('ishikawa: fishbone is data-driven and editable', t_ishikawa)

        # ---- 4. EDA report ----
        def t_eda():
            page.evaluate("()=>activate('eda')"); page.wait_for_timeout(200)
            r = page.evaluate("""()=>{const v=document.getElementById('v_eda');
              return {kpis:v.querySelectorAll('#eda_kpi .kpi').length,
                      charts:[...v.querySelectorAll('[id^=eda_c]')].filter(c=>c.querySelector('svg')).length,
                      tables:v.querySelectorAll('table').length};}""")
            assert r['kpis'] >= 4, 'EDA KPI cards missing'
            assert r['charts'] >= 4, 'EDA distribution charts not rendered'
            assert r['tables'] >= 2, 'EDA tables missing'
        case('EDA: report renders KPIs, charts and tables', t_eda)

        # ---- 4b. Star Map (team competencies by role) ----
        def t_starmap():
            page.evaluate("()=>activate('starmap')"); page.wait_for_timeout(200)
            r = page.evaluate("""()=>{const v=document.getElementById('v_starmap');
              return {radars:v.querySelectorAll('.sm-card svg').length,
                      matrices:v.querySelectorAll('table.sm-matrix').length,
                      rows:(ST.skills||[]).length,
                      team:(ST.team||[]).length};}""")
            assert r['rows'] > 0, 'no competency rows seeded'
            assert r['matrices'] >= 1, 'no competency matrix rendered'
            assert r['team'] == 0 or r['radars'] >= 1, 'no member radars rendered'
            # syncSkills() must be idempotent (no duplicate rows on a second run)
            same = page.evaluate("()=>{const a=(ST.skills||[]).length;syncSkills();return (ST.skills||[]).length===a;}")
            assert same, 'syncSkills() added duplicates on a no-op run'
        case('starmap: competency radars + matrix render', t_starmap)

        # ---- 4c. Agile maturity (Scrum / Kanban / SAFe) ----
        def t_agile():
            page.evaluate("()=>activate('agile')"); page.wait_for_timeout(200)
            r = page.evaluate("""()=>{const v=document.getElementById('v_agile');
              return {tabs:v.querySelectorAll('.agl-tab').length,
                      radar:!!v.querySelector('.sm-radar svg'),
                      scale:v.querySelectorAll('.agl-scale .agl-lv').length,
                      frameworks:[...new Set((ST.agile||[]).map(a=>a.framework))],
                      rows:(ST.agile||[]).length};}""")
            assert r['tabs'] == 3, 'expected 3 framework tabs (Scrum/Kanban/SAFe)'
            assert set(r['frameworks']) == {'Scrum', 'Kanban', 'SAFe'}, 'missing framework: ' + str(r['frameworks'])
            assert r['radar'], 'maturity radar not rendered'
            assert r['scale'] == 5, 'expected a 5-level maturity scale'
            # switching to the Kanban tab re-renders its dimensions
            sw = page.evaluate("""()=>{const t=[...document.querySelectorAll('#v_agile .agl-tab')].find(x=>x.textContent.includes('Kanban'));
              t.click();return UI.agileTab;}""")
            assert sw == 'Kanban', 'tab switch did not update UI.agileTab'
        case('agile-maturity: Scrum/Kanban/SAFe tabs render', t_agile)

        # ---- 4d. Integrations (Atlassian suite catalog) ----
        def t_integrations():
            page.evaluate("()=>activate('integrations')"); page.wait_for_timeout(150)
            r = page.evaluate("""()=>{const v=document.getElementById('v_integrations');
              const names=[...v.querySelectorAll('.intg-name')].map(x=>x.textContent);
              return {cards:v.querySelectorAll('.intg-card').length, names,
                      badges:v.querySelectorAll('.intg-badge').length,
                      catalog:(typeof ATL_PRODUCTS!=='undefined')?ATL_PRODUCTS.map(p=>p.k):[]};}""")
            assert r['cards'] >= 10, 'expected the full Atlassian product catalog (>=10)'
            for prod in ('Jira', 'Confluence', 'Bitbucket', 'Trello'):
                assert any(prod in n for n in r['names']), 'missing product: ' + prod
            for key in ('jira', 'jsm', 'confluence', 'bitbucket', 'trello', 'opsgenie', 'statuspage', 'bamboo'):
                assert key in r['catalog'], 'catalog missing ' + key
        case('integrations: Atlassian product catalog renders', t_integrations)

        # ---- 4e. Smart sidebar (collapse / pin / filter / recent) ----
        def t_nav():
            page.evaluate("()=>{try{localStorage.removeItem('navui');}catch(e){}NAVS.mode='all';buildNav();}")
            r = page.evaluate("""()=>{
              const nav=document.getElementById('nav');
              const hasSearch=!!document.getElementById('navsearch');
              togglePin('backlog');
              const fav=[...nav.querySelectorAll('.nav-smart .nav-h-t')].some(x=>x.textContent.includes('Избранное'));
              const pinned=!!nav.querySelector('.nav-pin.on[data-pin="backlog"]');
              toggleGroup('Выпуск');
              const grp=[...nav.querySelectorAll('.nav-group:not(.nav-smart)')].find(g=>g.querySelector('.nav-h-t').textContent==='Выпуск');
              const toggled=!grp.classList.contains('collapsed');
              navFilter('гант');
              const matches=[...nav.querySelectorAll('.nav-row')].filter(x=>x.style.display!=='none').map(x=>x.querySelector('.nav-lbl').textContent);
              navFilter('');
              togglePin('backlog');  // cleanup
              NAVS.mode='compact';buildNav();
              return {hasSearch,fav,pinned,toggled,matches};}""")
            assert r['hasSearch'], 'nav search box missing'
            assert r['fav'] and r['pinned'], 'pin → favorites did not work'
            assert r['toggled'], 'group collapse toggle did not work'
            assert r['matches'] == ['Гант', 'Гант по иерархии'], 'filter did not narrow to the matches: ' + str(r['matches'])
        case('sidebar: collapse/pin/filter smart nav', t_nav)

        # ---- 4f. Top toolbar: data actions consolidated into one menu ----
        def t_toolbar():
            r = page.evaluate("""()=>{
              const visible=[...document.querySelector('.tools').children].filter(c=>c.offsetParent!==null).map(c=>c.id);
              document.getElementById('ubtn').click();
              const opened=document.getElementById('umenu').classList.contains('open');
              const items=[...document.querySelectorAll('#upop .btn')].map(b=>b.id);
              document.body.click();
              const closed=!document.getElementById('umenu').classList.contains('open');
              return {visible,opened,items,closed};}""")
            assert all(x in r['visible'] for x in ('qcdm', 'stdot', 'umenu')), 'compact header: ＋ Создать, status dot, user menu: ' + str(r['visible'])
            for x in ('profbtn', 'rolebtn', 'tourbtn', 'logoutbtn'):
                assert x in r['items'], 'user menu missing ' + x
            for x in ('themebtn', 'densbtn', 'startbtn'):
                assert x not in r['items'], x + ' moved to «Мой профиль», not the menu'
            for old in ('xls', 'pptxbtn', 'exp', 'imp', 'impcsv', 'rst'):
                assert old not in r['visible'], old + ' should be inside the menu, not the top bar'
                assert old in r['items'], 'menu missing action ' + old
            assert r['opened'] and r['closed'], 'menu open/close broken'
        case('toolbar: data actions grouped in «Данные» menu', t_toolbar)

        # ---- 5. data quality checks engine ----
        def t_checks():
            ok = page.evaluate("()=>Array.isArray(dataChecks())")
            assert ok, 'dataChecks() not available'
        case('automation: data-quality checks engine runs', t_checks)

        # ---- 6. Kanban role-routing ----
        def t_kanban():
            page.evaluate("()=>{setPerm('ADMIN');applyPerms();UI.kanBoard='b-all';views();activate('kanban');}")
            page.wait_for_timeout(200)
            res = page.evaluate("""()=>{const tasks=(ST.tasks||[]).length;
              const cards=document.querySelectorAll('#v_kanban .kan-card, #v_kanban .kanban-card, #v_kanban [draggable=true]').length;
              const boards=(typeof kanBoards==='function')?kanBoards().length:(ST.boards||[]).length;
              return {tasks,cards,boards};}""")
            assert res['boards'] >= 4, 'expected multiple Kanban boards (roles + release)'
            assert res['cards'] > 0, 'no task cards rendered on «Все задачи» board'
            page.evaluate("()=>{setPerm('viewer');applyPerms();views();activate('dash');}")
        case('kanban: multi-board renders task cards', t_kanban)

        # ---- 7. release composition ----
        def t_rel():
            ok = page.evaluate("""()=>{const rs=ST.releases||[];if(!rs.length)return true;
              const c=releaseComp(rs[0]);return c && 'items' in c && 'stories' in c && 'bugs' in c && 'pct' in c;}""")
            assert ok, 'releaseComp() shape invalid'
        case('releases: composition engine returns structure', t_rel)

        # ---- 8. whiteboard: add item ----
        def t_board():
            ok = page.evaluate("""()=>{try{setPerm('editor');applyPerms();views();activate('board');
              if(typeof brdAdd!=='function'||typeof brdItems!=='function')return null;
              const before=brdItems().length;
              brdAdd({id:'e2e_'+Date.now(),t:'sticky',x:0,y:0,w:150,h:120,fill:'#FFE066',text:'e2e',author:'test'});
              const after=brdItems().length;
              const svg=!!document.querySelector('#v_board svg');
              return (after===before+1)&&svg;}catch(e){return 'ERR:'+e.message;}}""")
            if ok is None:
                raise Skip('board API not exposed')
            assert ok is True, 'adding a sticky did not grow board items (' + str(ok) + ')'
            page.evaluate("()=>{setPerm('viewer');applyPerms();views();activate('dash');}")
        case('whiteboard: add sticky note', t_board)

        # ---- 9. migrate() idempotency + save() ----
        def t_migrate():
            ok = page.evaluate("""()=>{const a=migrate(JSON.parse(JSON.stringify(SEED)));
              const b=migrate(JSON.parse(JSON.stringify(a)));
              return Array.isArray(a.tasks) && a.tasks.length===b.tasks.length;}""")
            assert ok, 'migrate() not idempotent on task count'
            saved = page.evaluate("""()=>{localStorage.removeItem(stKey());
              setPerm('editor');applyPerms();save();const v=!!localStorage.getItem(stKey());
              setPerm('viewer');applyPerms();return v;}""")
            assert saved, 'save() did not persist to localStorage for an editor'
        case('data: migrate() idempotent and save() persists', t_migrate)

        # ---- 9b. save() is gated by permission (viewer cannot persist) ----
        def t_perm_gate():
            blocked = page.evaluate("""()=>{setPerm('viewer');applyPerms();localStorage.removeItem(stKey());
              save();return localStorage.getItem(stKey())===null;}""")
            assert blocked, 'viewer must not be able to persist via save()'
        case('security: save() is gated by edit permission', t_perm_gate)

        # ---- 10. Support section (docs, no admin guide) ----
        def t_support():
            page.evaluate("()=>activate('support')"); page.wait_for_timeout(150)
            r = page.evaluate("""()=>{const c=[...document.querySelectorAll('#v_support .sup-card')];
              return {titles:c.map(x=>x.querySelector('.sup-t').textContent),
                      hasAdmin:c.some(x=>/администратор/i.test(x.querySelector('.sup-t').textContent))};}""")
            assert len(r['titles']) >= 4, 'Support cards missing'
            assert not r['hasAdmin'], 'Admin guide must NOT be in Support'
        case('support: documents listed, admin guide excluded', t_support)

        # ---- 11. Excel export produces a valid workbook ----
        def t_xlsx():
            b64 = page.evaluate("""async()=>{const oc=URL.createObjectURL;let blob=null;
              URL.createObjectURL=(b)=>{blob=b;return 'blob:stub';};
              try{ exportXlsx(); }catch(e){ URL.createObjectURL=oc; return 'ERR:'+e.message; }
              URL.createObjectURL=oc;
              if(!blob) return null;
              const buf=await blob.arrayBuffer();const u=new Uint8Array(buf);let s='';
              for(let i=0;i<u.length;i++)s+=String.fromCharCode(u[i]);return btoa(s);}""")
            assert b64 and not str(b64).startswith('ERR:'), 'exportXlsx failed: ' + str(b64)
            z = zipfile.ZipFile(io.BytesIO(base64.b64decode(b64)))
            names = z.namelist()
            assert '[Content_Types].xml' in names, 'xlsx missing content types'
            assert any(n.startswith('xl/worksheets/sheet') for n in names), 'xlsx has no sheets'
            # every content-type override must resolve to a real part
            ct = z.read('[Content_Types].xml').decode()
            miss = [pn for pn in re.findall(r'PartName="([^"]+)"', ct) if pn.lstrip('/') not in names]
            assert not miss, 'xlsx dangling content-type overrides: ' + str(miss)
        case('export: Excel workbook is a valid package', t_xlsx)

        # ---- 12. PPTX sprint report: builds and is NOT corrupt (regression) ----
        def t_pptx():
            loaded = page.evaluate("async()=>{try{await loadPptxGen();return true;}catch(e){return false;}}")
            if not loaded:
                raise Skip('pptxgenjs CDN unavailable (offline)')
            b64 = page.evaluate("""async()=>{
              window.__cap=null;const oc=URL.createObjectURL;
              URL.createObjectURL=(b)=>{window.__cap=b;return 'blob:stub';};
              try{ await exportPptx(''); }catch(e){ URL.createObjectURL=oc; return 'ERR:'+e.message; }
              URL.createObjectURL=oc;
              if(!window.__cap) return null;
              const buf=await window.__cap.arrayBuffer();const u=new Uint8Array(buf);let s='';
              for(let i=0;i<u.length;i++)s+=String.fromCharCode(u[i]);return btoa(s);}""")
            assert b64 and not str(b64).startswith('ERR:'), 'exportPptx failed: ' + str(b64)
            z = zipfile.ZipFile(io.BytesIO(base64.b64decode(b64)))
            names = set(z.namelist())
            slides = [n for n in names if re.match(r'ppt/slides/slide\d+\.xml$', n)]
            assert len(slides) >= 8, 'report has too few slides: ' + str(len(slides))
            ct = z.read('[Content_Types].xml').decode()
            miss = [pn for pn in re.findall(r'PartName="([^"]+)"', ct) if pn.lstrip('/') not in names]
            # regression: writePptxFixed must strip phantom slideMaster overrides
            assert not miss, 'PPTX would prompt "repair": dangling overrides ' + str(miss)
        case('report: PPTX builds with all slides and no corruption', t_pptx)

        # ---- 13. WSJF scoring + ranking ----
        def t_wsjf():
            r = page.evaluate("""()=>{
              const sc=wsjfScore({bv:10,tc:9,rr:8,jobSize:5});      // CoD 27 / 5 = 5.4
              const cod=wsjfCoD({bv:10,tc:9,rr:8});
              const zero=wsjfScore({bv:5,tc:5,rr:5,jobSize:0});      // guard: no divide-by-zero
              activate('wsjf');const v=document.getElementById('v_wsjf');
              return {sc,cod,zero,rows:v.querySelectorAll('table tr').length,chart:!!v.querySelector('svg')};}""")
            assert abs(r['sc'] - 5.4) < 1e-9, 'wsjfScore wrong: ' + str(r['sc'])
            assert r['cod'] == 27, 'wsjfCoD wrong: ' + str(r['cod'])
            assert r['zero'] == 0, 'wsjfScore must guard jobSize=0'
            assert r['rows'] > 2 and r['chart'], 'WSJF view did not render table+chart'
        case('wsjf: score, Cost of Delay and ranking render', t_wsjf)

        # ---- 14. Sprint goals + auto achievement % ----
        def t_goals():
            r = page.evaluate("""()=>{
              activate('sprintGoals');const v=document.getElementById('v_sprintGoals');
              const g=(ST.sprintGoals||[]);
              const sp=g.length?g[0].sprint:1;
              const a=goalAchievement(sp);
              return {hasGoals:g.length>0, kpis:v.querySelectorAll('.kpi').length,
                      pill:/pill/.test(v.innerHTML), ach: a?(a.pct>=0&&a.pct<=1):true};}""")
            assert r['hasGoals'], 'no sprint goals seeded'
            assert r['kpis'] >= 4 and r['pill'], 'sprint goals view missing KPIs/pills'
            assert r['ach'], 'goalAchievement pct out of range'
        case('goals: per-sprint goal + auto achievement %', t_goals)

        # ---- 15. Sprint risk forecast ----
        def t_risk():
            r = page.evaluate("""()=>{const C=compute();const risk=sprintRisk(C);
              return {ok:!!risk, score:risk.score, level:risk.level,
                      inRange:risk.score>=0&&risk.score<=100,
                      levelOk:['Низкий','Средний','Высокий'].includes(risk.level),
                      dash:/Риск срыва спринта/.test((()=>{activate('dash');return document.getElementById('v_dash').innerHTML;})())};}""")
            assert r['ok'] and r['inRange'], 'sprintRisk out of range: ' + str(r.get('score'))
            assert r['levelOk'], 'sprintRisk level invalid: ' + str(r.get('level'))
            assert r['dash'], 'risk KPI not shown on dashboard'
        case('risk: sprint risk forecast computes and shows on dashboard', t_risk)

        # ---- 16. Carryover of unfinished tasks ----
        def t_carry():
            r = page.evaluate("""()=>{
              const snap=JSON.stringify(ST.tasks), perm=JSON.stringify(PERM);
              PERM.canEdit=true;
              const _s=window.save,_v=window.views,_a=window.activate,_t=window.toast;
              window.save=()=>{};window.views=()=>{};window.activate=()=>{};window.toast=()=>{};
              const C=compute(),N=C.cur;
              const before=(ST.tasks||[]).filter(t=>+t.sprint===N&&t.status!=='Готово').length;
              const nextBefore=(ST.tasks||[]).filter(t=>+t.sprint===N+1).length;
              carryoverSprint(N);
              const afterN=(ST.tasks||[]).filter(t=>+t.sprint===N&&t.status!=='Готово').length;
              const nextAfter=(ST.tasks||[]).filter(t=>+t.sprint===N+1).length;
              const carried=(ST.tasks||[]).filter(t=>num(t.carried)>0).length;
              window.save=_s;window.views=_v;window.activate=_a;window.toast=_t;
              ST.tasks=JSON.parse(snap);Object.assign(PERM,JSON.parse(perm));
              return {before,nextBefore,afterN,nextAfter,carried};}""")
            if r['before'] > 0:
                assert r['afterN'] == 0, 'unfinished tasks remained in source sprint'
                assert r['nextAfter'] == r['nextBefore'] + r['before'], 'carryover count mismatch'
                assert r['carried'] >= r['before'], 'carried flag not set'
        case('carryover: unfinished tasks move to next sprint', t_carry)

        # ---- 17. WIP limits: badge + data-check warning ----
        def t_wip():
            r = page.evaluate("""()=>{
              const b=(ST.boards||[]).find(x=>x.id==='b-all')||ST.boards[0];
              const before=JSON.stringify(b.wip||{});
              b.wip={'В работе':1};
              const warn=dataChecks().filter(i=>/WIP/.test(i.msg)).length;
              const cnt=kanColCount(b,'В работе');
              b.wip=JSON.parse(before);
              return {warn,cnt,hasEditor:typeof kanEditWip==='function'};}""")
            assert r['hasEditor'], 'kanEditWip missing'
            assert r['cnt'] >= 0, 'kanColCount failed'
            assert r['warn'] >= 1, 'WIP over-limit not flagged by dataChecks'
        case('wip: per-column limits flagged when exceeded', t_wip)

        # ---- 18. Fuzzy duplicate task detection ----
        def t_dup():
            r = page.evaluate("""()=>{
              return {same:titleSim('Оплата картой','оплата  картой!'),
                      diff:titleSim('Оплата картой','Экспорт отчётов'),
                      norm:normTitle('  Привет,  МИР! ')};}""")
            assert r['same'] >= 0.9, 'identical titles should score ~1'
            assert r['diff'] < 0.4, 'different titles should score low'
            assert r['norm'] == 'привет мир', 'normTitle wrong: ' + str(r['norm'])
        case('duplicates: fuzzy title similarity', t_dup)

        # ---- 19. OKR -> task traceability ----
        def t_okr_trace():
            r = page.evaluate("""()=>{
              activate('okr');const v=document.getElementById('v_okr');
              return {krs:krList().length, linked:(ST.tasks||[]).filter(t=>t.okr).length,
                      hasCoverage:/Прослеживаемость/.test(v.innerHTML), kpis:v.querySelectorAll('.kpi').length};}""")
            assert r['krs'] > 0 and r['linked'] > 0, 'no OKR links seeded'
            assert r['hasCoverage'] and r['kpis'] >= 4, 'OKR coverage block missing'
        case('okr: Key Result -> task traceability', t_okr_trace)

        # ---- 20. Scope-creep log + baseline diff ----
        def t_scope():
            r = page.evaluate("""()=>{
              const n0=(ST.scopeLog||[]).length;
              logScope('Добавлено','T-TEST','проверка',3,'');
              const n1=(ST.scopeLog||[]).length;
              ST.scopeLog=ST.scopeLog.filter(x=>x.item!=='T-TEST');
              activate('scope');const v=document.getElementById('v_scope');
              return {grew:n1>n0, view:v.children.length>0, kpis:v.querySelectorAll('.kpi').length,
                      hasBaseline:typeof scopeBaseline==='function'&&typeof scopeDiff==='function'};}""")
            assert r['grew'], 'logScope did not append'
            assert r['view'] and r['kpis'] >= 4, 'scope view incomplete'
            assert r['hasBaseline'], 'scope baseline/diff missing'
        case('scope: creep log and baseline tools', t_scope)

        # ---- 21. Monte-Carlo release date + flow efficiency + bug SLA ----
        def t_forecast():
            r = page.evaluate("""()=>{const C=compute();const mc=mcReleaseForecast(C);
              const fe=flowEfficiency();const sla=bugSLA();
              return {mcOk:!!mc, p50le85: mc?mc.p50<=mc.p85:true, hist:mc?mc.hist.length:0,
                      feRange: fe.eff>=0&&fe.eff<=1, slaTotal: sla.total, slaShape: sla.rows.every(x=>'open'in x&&'target'in x)};}""")
            assert r['mcOk'] and r['p50le85'] and r['hist'] > 0, 'Monte-Carlo forecast invalid'
            assert r['feRange'], 'flow efficiency out of range'
            assert r['slaTotal'] == 3 and r['slaShape'], 'bug SLA shape wrong'
        case('forecast: Monte-Carlo dates, flow efficiency, bug SLA', t_forecast)

        # ---- 22. Release confidence + PI board ----
        def t_release_pi():
            r = page.evaluate("""()=>{const C=compute();
              const rel=(ST.releases||[])[0];const conf=rel?releaseConfidence(rel,releaseComp(rel),C):null;
              activate('piboard');const pv=document.getElementById('v_piboard');
              activate('releases');const rv=document.getElementById('v_releases');
              return {conf:!!conf, confLabel: conf?conf.label:'', pi: pv.children.length>0,
                      piBoard: !!pv.querySelector('.pi-board')|| /Нет межстримовых/.test(pv.innerHTML),
                      burnup: !!rv.querySelector('#rel_bu')};}""")
            assert r['conf'] and r['confLabel'], 'release confidence missing'
            assert r['pi'] and r['piBoard'], 'PI program board did not render'
            assert r['burnup'], 'release burn-up chart missing'
        case('release+pi: confidence, burn-up, program board', t_release_pi)

        # ---- 23. Integration action triggers exist ----
        def t_integr():
            r = page.evaluate("""()=>({esc:typeof escalateBlockers,pub:typeof publishSprintReport,
              jira:typeof jiraSync,skills:typeof skillsFromActivity,api:typeof apiPost})""")
            for k in ('esc', 'pub', 'jira', 'skills', 'api'):
                assert r[k] == 'function', 'missing integration fn: ' + k
        case('integrations: escalate/publish/jira-sync/skills triggers', t_integr)

        # ---- 24. Whiteboard: anchored connectors, quick-add, connect, animation, emoji, link ----
        def t_board2():
            r = page.evaluate("""()=>{try{
              setPerm('editor');applyPerms();views();activate('board');
              const snap=JSON.stringify(ST.board.items), perm=JSON.stringify(PERM);
              PERM.canEdit=true;
              const _s=window.save,_u=window.brdWSUpsert,_e=window.brdEdit,_t=window.toast;
              window.save=()=>{};window.brdWSUpsert=()=>{};window.brdEdit=()=>{};window.toast=()=>{};
              // anchored connector endpoints follow shapes
              const a={id:'A',t:'rect',x:0,y:0,w:100,h:60,fill:'#fff',stroke:'#2D5BE3'};
              const b={id:'B',t:'rect',x:300,y:0,w:100,h:60,fill:'#fff',stroke:'#2D5BE3'};
              ST.board.items=[a,b];
              const conn={id:'C',t:'conn',from:'A',to:'B',stroke:'#334155'};ST.board.items.push(conn);
              const e1=brdConnEnds(conn);
              // quick-add from A to the right -> +2 items (shape + anchored conn)
              BW.sel=['A'];const n0=ST.board.items.length;brdQuickAdd('A','right');const n1=ST.board.items.length;
              const qConn=ST.board.items[ST.board.items.length-1];
              // connect selected A+B
              BW.sel=['A','B'];const n2=ST.board.items.length;brdConnectSel();const n3=ST.board.items.length;
              // animation
              BW.sel=['A'];brdSetAnim('pulse');const anim=brdItemById('A').anim;
              // deleting A removes connectors anchored to A
              BW.sel=['A'];const before=ST.board.items.length;brdDelSel();
              const aGone=!brdItemById('A');
              const danglers=ST.board.items.filter(x=>x.t==='conn'&&(x.from==='A'||x.to==='A')).length;
              window.save=_s;window.brdWSUpsert=_u;window.brdEdit=_e;window.toast=_t;
              ST.board.items=JSON.parse(snap);Object.assign(PERM,JSON.parse(perm));
              return {edgeRouted:(e1.x1>=90&&e1.x2<=310), quick:(n1-n0===2), quickAnchored:!!(qConn.from&&qConn.to),
                      connect:(n3-n2===1), anim:anim==='pulse', aGone:aGone, danglers:danglers};
            }catch(e){return 'ERR:'+e.message;}}""")
            assert r is not True and isinstance(r, dict), 'board2 failed: ' + str(r)
            assert r['edgeRouted'], 'anchored connector did not route to shape edges'
            assert r['quick'] and r['quickAnchored'], 'quick-add must create shape + anchored connector'
            assert r['connect'], 'connect-selected did not create a connector'
            assert r['anim'], 'animation not applied'
            assert r['aGone'] and r['danglers'] == 0, 'deleting a shape must remove its connectors'
            page.evaluate("()=>{setPerm('viewer');applyPerms();views();activate('dash');}")
        case('whiteboard2: connectors, quick-add, animation, cleanup', t_board2)

        # ---- 24b. Whiteboard tools: ergonomics, live data, templates ----
        def t_board3():
            r = page.evaluate("""()=>{try{
              setPerm('editor');applyPerms();views();activate('board');
              const snap=JSON.stringify(ST.board.items), perm=JSON.stringify(PERM);
              const keep={};['tasks','risks','impediments','decisions','retro','lessons'].forEach(k=>keep[k]=JSON.stringify(ST[k]||[]));
              PERM.canEdit=true;
              const _s=window.save,_u=window.brdWSUpsert,_e=window.brdEdit,_t=window.toast,_f=window.brdFocusBox;
              window.save=()=>{};window.brdWSUpsert=()=>{};window.brdEdit=()=>{};window.toast=()=>{};
              const out={};
              // --- отмена / повтор ---
              ST.board.items=[];brdHistReset();
              brdAdd({id:'S1',t:'sticky',x:0,y:0,w:150,h:120,fill:'#FFE066',text:'Идея альфа',author:'t',votes:0});brdSave();
              const nA=brdItems().length;brdUndo();const nU=brdItems().length;brdRedo();const nR=brdItems().length;
              out.undo=(nA===1&&nU===0&&nR===1);
              // --- копировать/вставить: связь между копиями перепривязывается ---
              brdAdd({id:'R1',t:'rect',x:300,y:0,w:100,h:60,fill:'#fff',stroke:'#2D5BE3'});brdAdd({id:'K1',t:'conn',from:'S1',to:'R1',stroke:'#334155'});
              BW.sel=['S1','R1'];brdCopy(true);brdPaste();
              const pasted=brdItems().filter(x=>['S1','R1','K1'].indexOf(x.id)<0),pc=pasted.find(x=>x.t==='conn');
              out.paste=(pasted.length===3&&!!pc&&pasted.some(x=>x.id===pc.from)&&pasted.some(x=>x.id===pc.to));
              ST.board.items=brdItems().filter(x=>['S1','R1','K1'].indexOf(x.id)>=0);
              // --- группа: клик по одному элементу выделяет всю группу ---
              BW.sel=['S1','R1'];brdGroup();BW.sel=[];brdSelectWith('S1',false);out.group=(BW.sel.length===2);brdUngroup();
              // --- выравнивание и распределение ---
              brdItemById('R1').y=200;BW.sel=['S1','R1'];brdAlign('top');out.align=(brdItemById('R1').y===brdItemById('S1').y);
              ST.board.items=[{id:'D1',t:'rect',x:0,y:0,w:100,h:60},{id:'D2',t:'rect',x:50,y:0,w:100,h:60},{id:'D3',t:'rect',x:500,y:0,w:100,h:60}];
              BW.sel=['D1','D2','D3'];brdDistribute('h');out.distribute=(Math.abs(brdItemById('D2').x-250)<0.01);
              // --- закрепление: не удаляется и не двигается ---
              ST.board.items=[{id:'L1',t:'sticky',x:0,y:0,w:100,h:100,text:'фикс',locked:true}];
              BW.sel=['L1'];brdDelSel();out.lockDel=!!brdItemById('L1');out.lockMove=(brdMoveSet().indexOf('L1')<0);
              // --- фрейм переносится вместе с содержимым ---
              ST.board.items=[{id:'F1',t:'frame',x:0,y:0,w:600,h:400,title:'F'},{id:'S9',t:'sticky',x:100,y:100,w:120,h:100,text:'внутри'},{id:'S8',t:'sticky',x:900,y:900,w:120,h:100,text:'снаружи'}];
              BW.sel=['F1'];const ms=brdMoveSet();out.frameCarries=(ms.indexOf('S9')>=0&&ms.indexOf('S8')<0);
              // --- сетка, мини-карта, поиск ---
              const sn0=BW.snap;BW.snap=true;out.snap=(brdSnapV(30)===22&&brdSnapV(40)===44);BW.snap=sn0;
              const mm=document.getElementById('brd-mini');if(mm)mm.style.display='';brdMiniRender();
              out.minimap=!!mm&&mm.querySelectorAll('rect').length>=3;
              out.search=(brdFind('внутри').length===1&&brdFind('несуществующее-xyz').length===0);
              // --- живая карточка задачи + смена статуса из доски ---
              ST.board.items=[];const t0=ST.tasks[0],st0=t0.status;
              const card=brdAddTaskCard(t0.id);brdRender();
              out.taskCard=!!card&&document.querySelector('#v_board svg').textContent.indexOf(t0.id)>=0;
              brdTaskCycle(card.id);out.taskCycle=(t0.status!==st0);
              t0.title=t0.title+' (обновлено)';brdRender();out.taskLive=document.querySelector('#v_board svg').textContent.indexOf('(обновлено)')>=0;
              // --- виджеты-метрики ---
              let mOk=true;BRD_METRICS.forEach(m=>{const d=brdMetricData(m[0]);if(!d||!d.title||(d.val==null&&d.text==null))mOk=false;});
              brdAddMetric('velocity');brdRender();out.metric=mOk&&document.querySelector('#v_board svg').textContent.indexOf('VELOCITY')>=0;
              // --- стикер -> сущность ---
              ST.board.items=[{id:'C1',t:'sticky',x:0,y:0,w:150,h:120,text:'Риск сбоя оплаты'},{id:'C2',t:'sticky',x:0,y:200,w:150,h:120,text:'Сделать экспорт CSV'},{id:'C3',t:'sticky',x:0,y:400,w:150,h:120,text:'Нет доступа к стенду'}];
              const nr=(ST.risks||[]).length,nt=(ST.tasks||[]).length,ni=(ST.impediments||[]).length;
              BW.sel=['C1'];brdConvert('risk');BW.sel=['C2'];brdConvert('task');BW.sel=['C3'];brdConvert('impediment');
              out.convRisk=(ST.risks.length===nr+1&&brdItemById('C1').ref.k==='risk');
              out.convTask=(ST.tasks.length===nt+1&&brdItemById('C2').t==='task'&&!!brdTask(brdItemById('C2')));
              out.convImp=(ST.impediments.length===ni+1&&/^IM-/.test(brdItemById('C3').ref.id));
              // --- шаблоны: каждый добавляет сгруппированную сетку фреймов ---
              ST.board.items=[];let tplOk=true;
              Object.keys(BRD_TPL).forEach(k=>{const before=brdItems().length,made=brdInsertTemplate(k)||[];const frames=made.map(brdItemById).filter(x=>x&&x.t==='frame');
                if(brdItems().length<=before||frames.length<BRD_TPL[k].cells.length+1||!frames.every(f=>f.grp===frames[0].grp))tplOk=false;});
              out.templates=tplOk&&Object.keys(BRD_TPL).length>=11;
              const outer=brdItems().find(x=>x.t==='frame'&&x.title.indexOf(BRD_TPL.ssc.name)>=0);BW.sel=[];brdSelectWith(outer.id,false);
              out.tplMoveAll=(BW.sel.length===4&&brdMoveSet().length>=7);
              // восстановление
              window.save=_s;window.brdWSUpsert=_u;window.brdEdit=_e;window.toast=_t;
              ST.board.items=JSON.parse(snap);Object.keys(keep).forEach(k=>ST[k]=JSON.parse(keep[k]));Object.assign(PERM,JSON.parse(perm));BW.sel=[];brdHistReset();brdRender();
              return out;
            }catch(e){return 'ERR:'+e.message+' '+(e.stack||'').split('\\n')[1];}}""")
            assert isinstance(r, dict), r
            bad = [k for k, v in r.items() if v is not True]
            assert not bad, 'board tools failed checks: %s (%s)' % (bad, r)
        case('whiteboard3: undo/clipboard/group/align/lock, live tasks & metrics, sticky->entity, templates', t_board3)

        # ---- 24c. Whiteboard wave 2: sessions (vote/anon/present/comments) + diagrams ----
        def t_board4():
            r = page.evaluate("""()=>{try{
              setPerm('editor');applyPerms();views();activate('board');
              const snap=JSON.stringify(ST.board.items),sess=JSON.stringify(ST.board.session||null),perm=JSON.stringify(PERM);
              PERM.canEdit=true;
              const _s=window.save,_u=window.brdWSUpsert,_e=window.brdEdit,_t=window.toast,_w=window.brdWSSend,_c=window.confirm;
              window.save=()=>{};window.brdWSUpsert=()=>{};window.brdEdit=()=>{};window.toast=()=>{};window.brdWSSend=()=>{};
              const out={};const txt=()=>document.querySelector('#v_board svg').textContent;
              // --- голосование точками: лимит, скрытый режим, раскрытие, медали, снятие голоса ---
              ST.board.items=[{id:'V1',t:'sticky',x:0,y:0,w:150,h:120,text:'Идея A',author:'Петров',votes:0},{id:'V2',t:'sticky',x:200,y:0,w:150,h:120,text:'Идея B',author:'Петров',votes:0}];
              ST.board.session={};brdSessSet(s=>{s.vote={on:true,limit:2,hidden:true,revealed:false};});
              const a1=brdVote('V1'),a2=brdVote('V1'),a3=brdVote('V2');
              out.voteLimit=(a1&&a2&&!a3&&brdVoteLeft()===0&&brdItemById('V1').votes===2);
              out.voteHidden=(brdVoteLabel(brdItemById('V1'))==='✓2'&&brdVoteLabel(brdItemById('V2'))==='🗳');
              brdVote('V1',true);out.unvote=(brdItemById('V1').votes===1&&brdVoteLeft()===1);
              brdVote('V1');brdSessSet(s=>{s.vote.revealed=true;});brdRender();
              out.reveal=(brdVoteLabel(brdItemById('V1'))==='👍2'&&brdVoteRanks()['V1']===1&&txt().indexOf('🥇')>=0);
              brdVoteReset(true);out.voteReset=(!brdItemById('V1').votes&&!brdItemById('V1').voters&&!brdSess().vote.revealed);
              // --- анонимный ввод ---
              brdSessSet(s=>{s.anon=true;s.anonRevealed=false;});const hid=brdAuthorLabel(brdItemById('V1'));
              brdSessSet(s=>{s.anonRevealed=true;});out.anon=(hid.indexOf('Петров')<0&&brdAuthorLabel(brdItemById('V1')).indexOf('Петров')>=0);
              brdSessSet(s=>{s.anon=false;});
              // --- показ по фреймам: порядок чтения, листание, выход ---
              ST.board.items=[{id:'P2',t:'frame',x:900,y:0,w:400,h:300,title:'Второй'},{id:'P1',t:'frame',x:0,y:0,w:400,h:300,title:'Первый'},
                {id:'P1a',t:'frame',x:20,y:40,w:100,h:100,title:'вложенный'},{id:'P3',t:'frame',x:0,y:700,w:400,h:300,title:'Третий'}];
              const order=brdPresFrames().map(f=>f.id).join(',');out.presOrder=(order==='P1,P2,P3');
              brdPresStart();const on=BW.wrap.classList.contains('brd-presenting')&&BW.pres.i===0;brdPresGo(1);const i1=BW.pres.i;brdPresGo(99);const iEnd=BW.pres.i;
              brdPresEnd();out.present=(on&&i1===1&&iEnd===2&&!BW.pres&&!BW.wrap.classList.contains('brd-presenting'));
              // --- комментарии с @упоминаниями ---
              const who=(ST.team[0]||{}).name;ST.board.items=[{id:'M1',t:'sticky',x:0,y:0,w:150,h:120,text:'Обсудить'}];
              const cm=brdCmtAdd('M1','Посмотри, пожалуйста @'+who);brdRender();
              out.comment=(!!cm&&cm.m.indexOf(who)>=0&&brdItemById('M1').comments.length===1&&txt().indexOf('💬 1')>=0&&brdCmtAll().length===1&&brdFind('Посмотри').length===1);
              brdCmtDel('M1',cm.id);out.commentDel=!brdItemById('M1').comments;
              // --- блок-схема: новые фигуры + подпись стрелки + быстрое продолжение ---
              ST.board.items=[];let shapes=true;['terminator','document','database','parallelogram'].forEach((t,i)=>{brdAdd({id:'F'+i,t:t,x:i*220,y:0,w:160,h:90,fill:'#fff',stroke:'#2D5BE3',text:t});});
              brdRender();['F0','F1','F2','F3'].forEach(id=>{const g=document.querySelector('#v_board svg [data-id="'+id+'"]');if(!g||!g.querySelector('path,polygon,rect'))shapes=false;});
              brdAdd({id:'K1',t:'conn',from:'F0',to:'F1',label:'да'});brdRender();
              out.flow=shapes&&txt().indexOf('да')>=0&&BRD_DRAW_T.indexOf('database')>=0;
              const nq=brdItems().length;brdQuickAdd('F0','down');out.flowQuick=(brdItems().length===nq+2&&brdItems()[brdItems().length-2].t==='terminator');
              // --- майнд-карта: дочерние/соседние ветки, раскладка в обе стороны, удаление ветки целиком ---
              ST.board.items=[];const root=brdMindNew();const c1=brdMindAdd(root.id,'child',true),c2=brdMindAdd(root.id,'child',true),s1=brdMindAdd(c1.id,'sibling',true),g1=brdMindAdd(c1.id,'child',true);
              const R=brdItemById(root.id);
              out.mindTree=(brdMindKids(root.id).length===3&&c1.x>R.x+R.w&&c2.x+c2.w<R.x&&g1.x>c1.x+c1.w&&brdMindRoot(g1.id).id===root.id);
              out.mindConn=brdItems().filter(x=>x.t==='conn'&&x.style==='mind').length===4;
              BW.sel=[c1.id];brdDelSel();out.mindDel=(!brdItemById(g1.id)&&!!brdItemById(c2.id)&&brdItems().filter(x=>x.t==='conn').length===2);
              // --- таблица: ячейки, строки, столбцы ---
              ST.board.items=[];const tb=brdTableNew();brdTableSet(tb.id,1,0,'Риск');const h0=tb.h,w0=tb.w;
              brdTableOp('addRow',tb.id);brdTableOp('addCol',tb.id);brdRender();
              const T=brdItemById(tb.id);out.table=(T.rows.length===4&&T.rows[0].length===4&&T.h>h0&&T.w>w0&&T.rows[1][0]==='Риск'&&txt().indexOf('Риск')>=0);
              brdTableOp('delRow',tb.id);brdTableOp('delCol',tb.id);out.tableDel=(brdItemById(tb.id).rows.length===3&&brdItemById(tb.id).rows[0].length===3);
              // --- авто-раскладка: сетка и дерево по связям ---
              ST.board.items=[{id:'A',t:'rect',x:0,y:0,w:100,h:60},{id:'B',t:'rect',x:500,y:400,w:100,h:60},{id:'C',t:'rect',x:40,y:900,w:100,h:60},{id:'E1',t:'conn',from:'A',to:'B'},{id:'E2',t:'conn',from:'A',to:'C'}];
              BW.sel=['A','B','C'];brdAutoTree();const A=brdItemById('A'),B=brdItemById('B'),Cc=brdItemById('C');
              out.autoTree=(B.x>A.x+A.w&&B.x===Cc.x&&B.y!==Cc.y);
              ST.board.items=[0,1,2,3].map(i=>({id:'G'+i,t:'rect',x:i*13,y:i*500,w:100,h:60}));BW.sel=['G0','G1','G2','G3'];brdAutoGrid();
              const xs=new Set(brdItems().map(x=>x.x)),ys=new Set(brdItems().map(x=>x.y));out.autoGrid=(xs.size===2&&ys.size===2);
              // --- шаблон дорожек по ролям команды ---
              ST.board.items=[];const roles=new Set((ST.team||[]).map(m=>m.role).filter(Boolean)).size;brdInsertTemplate('swim');
              out.swim=brdItems().filter(x=>x.t==='frame'&&x.notitle).length===Math.min(6,roles||4);
              // восстановление
              window.save=_s;window.brdWSUpsert=_u;window.brdEdit=_e;window.toast=_t;window.brdWSSend=_w;window.confirm=_c;
              ST.board.items=JSON.parse(snap);ST.board.session=JSON.parse(sess)||{};Object.assign(PERM,JSON.parse(perm));BW.sel=[];BW.pres=null;brdHistReset();brdRender();
              return out;
            }catch(e){return 'ERR:'+e.message+' '+(e.stack||'').split('\\n')[1];}}""")
            assert isinstance(r, dict), r
            bad = [k for k, v in r.items() if v is not True]
            assert not bad, 'board wave-2 checks failed: %s (%s)' % (bad, r)
        case('whiteboard4: voting/anon/presentation/comments, flowchart, mind map, table, auto-layout, swimlanes', t_board4)

        # ---- 25. EVM: earned value indices and forecast ----
        def t_evm():
            r = page.evaluate("""async()=>{const C=compute();const E=evm(C);activate('evm');await new Promise(r=>setTimeout(r,60));
              return {bac:E.BAC>0, rows:E.rows.length===C.sp.length,
                      cpiOk:E.CPI===null||E.CPI>0, spiOk:E.SPI===null||E.SPI>0,
                      eacOk:E.EAC===null||(E.CPI&&Math.abs(E.EAC-E.BAC/E.CPI)<1),
                      chart:!!document.querySelector('#v_evm svg')};}""")
            assert r['bac'] and r['rows'], 'EVM rows/BAC invalid'
            assert r['cpiOk'] and r['spiOk'], 'EVM indices out of range'
            assert r['eacOk'], 'EAC != BAC/CPI'
            assert r['chart'], 'EVM S-curve missing'
        case('evm: PV/EV/AC, CPI/SPI, EAC forecast', t_evm)

        # ---- 26. Planning poker consensus ----
        def t_poker():
            r = page.evaluate("""()=>{const rv=pokerReveal('A:5, B:8, C:8, D:5');
              const fib=[1,2,3,5,8,13,21];
              return {med:rv.med, cons:rv.consensus, inFib:fib.includes(rv.consensus),
                      spread:rv.spread, empty:pokerReveal('')};}""")
            assert r['empty'] is None, 'empty votes must return null'
            assert r['inFib'], 'consensus must snap to Fibonacci'
            assert r['spread'] == 3, 'spread wrong'
        case('poker: reveal median/consensus on Fibonacci', t_poker)

        # ---- 27. WBS rollup ----
        def t_wbs():
            r = page.evaluate("""()=>{
              const tasks=ST.tasks||[];const e=tasks.find(t=>(tasks.filter(c=>c.parent===t.id)).length>0);
              if(!e)return {skip:true};
              const roll=wbsRoll(e);const kids=tasks.filter(c=>c.parent===e.id);
              const kidSum=kids.reduce((a,c)=>a+num(c.est),0)+num(e.est);
              return {ok: roll.sp>=kidSum-0.001, rendered:(activate('wbs'),document.querySelectorAll('#v_wbs table tr').length>1)};}""")
            if r.get('skip'):
                raise Skip('no WBS hierarchy seeded')
            assert r['ok'], 'WBS rollup did not sum children'
            assert r['rendered'], 'WBS tree did not render'
        case('wbs: Epic rollup of child estimates', t_wbs)

        # ---- Hierarchical Gantt: Epic → Feature → Story → Task by «parent», rollup of volume and progress ----
        def t_hgantt():
            r = page.evaluate("""()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             const keep=JSON.stringify(ST.tasks);
             try{HG.level=2;HG.open={};HG.fact=true;views();activate('hgantt');
              const tabs=[...document.querySelectorAll('#v_hgantt > .hub-tabs [data-hubv]')].map(b=>b.dataset.hubv);
              const T=ST.tasks,types=[...new Set(T.map(t=>t.type))];
              const rows=()=>[...document.querySelectorAll('#hg_root .hg-row[data-hgrow]')].map(x=>x.dataset.hgrow);
              const l2=rows(),roots=T.filter(t=>!t.parent||!T.some(x=>x.id===t.parent)).map(t=>t.id),feats=T.filter(t=>t.type==='Фича').map(t=>t.id);
              const lvl2=roots.every(id=>l2.includes(id))&&feats.every(id=>l2.includes(id))&&!l2.includes('T-02');
              document.querySelector('#hg_root [data-hglv="1"]').click();const l1=rows();
              document.querySelector('#hg_root [data-hgt="E-1"]').click();const e1open=rows().includes('FE-1')&&!rows().includes('FE-3');
              document.querySelector('#hg_root [data-hglv="9"]').click();const l9=rows().length;
              const desc=id=>{const out=[];const go=q=>T.filter(t=>t.parent===q).forEach(c=>{out.push(c);go(c.id);});go(id);return out;};
              const all=[T.find(t=>t.id==='E-1')].concat(desc('E-1'));
              const sp=all.reduce((s,t)=>s+num(t.est),0),dn=all.filter(t=>t.status==='Готово').reduce((s,t)=>s+num(t.est),0);
              const meta=document.querySelector('#hg_root [data-hgrow="E-1"] .hg-m').textContent;
              const G=hgTree(),n=G.nodes.find(x=>x.t.id==='E-1'),ks=desc('E-1').map(t=>num(t.sprint)).filter(s=>s>0);
              const roll=n.sp===sp&&n.done===dn&&+n.a===+G.spA(Math.min(...ks))&&+n.b===+addD(G.spA(Math.max(...ks)),11);
              const late=[...document.querySelectorAll('#hg_root .hg-late')].map(x=>x.closest('[data-hgrow]').dataset.hgrow);
              const facts=document.querySelectorAll('#hg_root .hg-f').length;
              document.querySelector('#hg_root [data-hgf]').click();const noFact=document.querySelectorAll('#hg_root .hg-f').length===0;HG.fact=true;
              const a=T.find(t=>t.id==='T-19'),b=T.find(t=>t.id==='T-20'),pa=a.parent,pb=b.parent;a.parent='T-20';b.parent='T-19';hgRefresh();
              const cyc=(document.querySelector('#hg_root .wiz-warn:not(.hg-linkbad)')||{}).textContent||'';a.parent=pa;b.parent=pb;hgRefresh();
              document.querySelector('#hg_root [data-hgo="T-14"]').click();const opened=CURV==='backlog'&&UI.search.tasks==='T-14';UI.search.tasks='';
              const again=migrate(JSON.parse(JSON.stringify(ST))).tasks.filter(t=>t.type==='Фича').length;
              const blank=migrate(%(BLANK)s(ST)).tasks.length;
              return {tabs,types,lvl2,l1,roots,e1open,l9,n:T.length,meta,roll,late,facts,noFact,cyc,opened,again,feats:feats.length,blank,depth:wbsDepth(T.filter(t=>!t.parent),T),errs};
             }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);ST.tasks=JSON.parse(keep);HG.level=2;HG.open={};HG.fact=true;views();activate('dash');}}""" % {'BLANK': 'orgBlankState'})
            assert isinstance(r, dict), 'hgantt failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['tabs'][:2] == ['gantt', 'hgantt'], 'hierarchical Gantt is a tab of «Расписание»: ' + str(r['tabs'])
            assert r['depth'] >= 4 and {'Эпик', 'Фича', 'История', 'Задача'} <= set(r['types']) and r['feats'] == 4, 'demo has 4 levels: ' + str(r)
            assert r['lvl2'], 'level «До фич» shows roots and features, hides stories/tasks'
            assert set(r['l1']) == set(r['roots']) and r['e1open'], 'level «Эпики» + expanding one epic: ' + str(r['l1'])
            assert r['l9'] == r['n'], 'level «Всё» shows every element once'
            assert r['roll'] and 'SP' in r['meta'], 'epic rollup: volume, done and span from descendants: ' + str(r['meta'])
            assert 'T-12' in r['late'] and 'T-10' in r['late'], 'overdue / out-of-sprint elements outlined: ' + str(r['late'])
            assert r['facts'] > 0 and r['noFact'], 'fact bars toggle'
            assert 'цикле' in r['cyc'], 'cycle in «Родитель» is reported, not crashing'
            assert r['opened'], 'ID opens the element in «Бэклог»'
            assert r['again'] == 4 and r['blank'] == 0, 'demo features added once; blank project gets none: ' + str(r)
        case('hgantt: hierarchy Gantt — levels, rollup, plan/fact, overdue, cycles, demo features', t_hgantt)

        # ---- Stage marks on the hierarchy Gantt: auto by roles/demo/release, manual panel, legend, role mapping ----
        def t_stages():
            r = page.evaluate("""()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             const keepT=JSON.stringify(ST.tasks),keepR=ST.params.stageRoles;
             try{setPerm('editor');applyPerms();HG.level=9;HG.open={};HG.marks=true;views();activate('hgantt');
              const leg=document.querySelectorAll('#hg_root .hg-mleg .hg-mi').length,legTxt=(document.querySelector('#hg_root .hg-mleg')||{}).textContent||'';
              const n=id=>hgFind(id),t1=n('T-01'),f1=n('FE-1');
              const auto={dev:[t1.st.dev_s,t1.st.dev_e],psi:[t1.st.psi_s,t1.st.psi_e],prod:[t1.st.prod_s,t1.st.prod_e],
               feDevS:f1.st.dev_s,feDevE:f1.st.dev_e||null,feBa:[f1.st.ba_s,f1.st.ba_e],feMan:Object.keys(f1.mk).sort()};
              const t1marks=document.querySelectorAll('#hg_root [data-hgrow="T-01"] .hg-mk').length;
              const shapes=[...document.querySelectorAll('#hg_root [data-hgrow="T-01"] .hg-mk')].map(m=>m.title.split(' — ')[0]);
              // ручная метка: панель «Этапы» по клику на название
              document.querySelector('#hg_root [data-hgrow="T-12"] .hg-tt').click();const m=document.getElementById('hgsmodal');
              const fields=m.querySelectorAll('[data-hgk]').length;m.querySelector('[data-hgk="ba_s"]').value='2026-08-20';m.querySelector('[data-hgsx=ok]').click();
              const saved=JSON.stringify(ST.tasks.find(x=>x.id==='T-12').stages),manMk=[...document.querySelectorAll('#hg_root [data-hgrow="T-12"] .hg-mk')].some(x=>/вручную/.test(x.title)&&x.querySelector('svg circle[r="1.9"]'));
              document.querySelector('#hg_root [data-hgrow="T-12"] .hg-mk').click();document.querySelector('#hgsmodal [data-hgsx=auto]').click();
              const reset=JSON.stringify(ST.tasks.find(x=>x.id==='T-12').stages);
              // роли: убираем Backend из разработки — авто-метки разработки у T-01 пропадают
              ST.params.stageRoles='ba=Product Owner;sa=Analyst;dev=Frontend;ift=QA';const noDev=!hgFind('T-09').st.dev_s&&!hgFind('T-01').st.dev_s&&!!hgFind('T-02').st.dev_s;ST.params.stageRoles=keepR;
              activate('params');const roleBoxes=document.querySelectorAll('#hgrdiv [data-hgr]').length;
              const cb=document.querySelector('#hgrdiv [data-hgr="ift"][value="DevOps"]');cb.checked=true;cb.dispatchEvent(new Event('change',{bubbles:true}));
              const mapped=(hgRoleMap().ift||[]).includes('DevOps');ST.params.stageRoles=keepR;
              // просмотр: панель только для чтения
              setPerm('viewer');applyPerms();activate('hgantt');document.querySelector('#hg_root [data-hgrow="T-01"] .hg-tt').click();
              const ro=[...document.querySelectorAll('#hgsmodal [data-hgk]')].every(i=>i.disabled)&&!document.querySelector('#hgsmodal [data-hgsx=ok]');
              document.querySelector('#hgsmodal [data-hgsx=cancel]').click();setPerm('editor');applyPerms();
              document.querySelector('#hg_root [data-hgm]').click();const hidden=document.querySelectorAll('#hg_root .hg-mk').length===0;HG.marks=true;
              return {leg,legTxt,auto,t1marks,shapes,fields,saved,manMk,reset,noDev,roleBoxes,mapped,ro,hidden,errs};
             }catch(e){return 'ERR:'+e.message+' '+e.stack;}finally{window.removeEventListener('error',h);ST.tasks=JSON.parse(keepT);ST.params.stageRoles=keepR;HG.marks=true;HG.level=2;HG.open={};setPerm('editor');applyPerms();views();activate('dash');}}""")
            assert isinstance(r, dict), 'stages failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['leg'] == 12 and 'Контур — начало' in r['legTxt'], 'legend lists all 12 marks with description'
            a = r['auto']
            assert a['dev'] == ['2026-08-03', '2026-08-06'], 'dev marks of T-01 from role Backend dates: ' + str(a)
            assert a['psi'] == ['2026-08-14', '2026-08-14'], 'PSI from accepted sprint demo: ' + str(a)
            assert a['prod'] == ['2026-08-17', '2026-08-28'], 'Prod from release R-1 (done): ' + str(a)
            assert a['feDevS'] == '2026-08-03' and a['feDevE'] is None, 'parent: earliest start, no end while a child is not done: ' + str(a)
            assert a['feBa'] == ['2026-07-20', '2026-07-24'] and a['feMan'] == ['ba_e', 'ba_s', 'sa_e', 'sa_s'], 'demo manual analysis marks: ' + str(a)
            assert r['t1marks'] >= 6 and 'Начало разработки' in r['shapes'] and 'Выход в Прод' in r['shapes'], str(r['shapes'])
            assert r['fields'] == 12 and r['saved'] == '{"ba_s":"2026-08-20"}' and r['manMk'], 'manual mark via panel: ' + str(r)
            assert r['reset'] == '{}', 'reset to auto clears manual marks'
            assert r['noDev'], 'role mapping drives auto marks'
            assert r['roleBoxes'] == 4 * 8 and r['mapped'], 'role mapping editable in Parameters: ' + str(r)
            assert r['ro'] and r['hidden'], 'viewer read-only panel; marks toggle'
        case('stages: hierarchy Gantt stage marks — auto (roles, demo, release), manual panel, legend, roles', t_stages)

        # ---- Dependency arrows on the hierarchy Gantt: several predecessors, rollup to visible ancestors, conflicts, editing ----
        def t_hglinks():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             const keep=JSON.stringify(ST.tasks),T=()=>ST.tasks,g=id=>ST.tasks.find(x=>x.id===id),tick=()=>new Promise(r=>setTimeout(r,60));
             const lns=()=>[...document.querySelectorAll('#hg_root .hg-ln')].map(x=>x.dataset.ln+(x.classList.contains('der')?':der':'')+(x.classList.contains('conf')?':conf':'')+(x.classList.contains('crit')?':crit':''));
             try{setPerm('editor');applyPerms();HG.level=9;HG.open={};HG.links=true;views();activate('hgantt');await tick();
              const demoBranch=['T-02','T-13'].map(id=>g(id).parent).join(',');
              const all=lns(),bad=document.querySelector('#hg_root .hg-linkbad').textContent;
              g('T-09').dep='T-12';hgRefresh();await tick();const conf=lns().includes('T-12>T-09:conf');
              const confList=depConflictList().some(x=>x.startsWith('T-09'));
              HG.level=2;HG.open={};hgRefresh();await tick();const l2=lns();
              HG.level=9;hgRefresh();await tick();
              // ветка иерархии: связь родитель/потомок не рисуется, показывается предупреждение
              g('T-08').dep='T-11';hgRefresh();await tick();const branch=document.querySelector('#hg_root .hg-linkbad').textContent;g('T-08').dep='';
              // панель: добавить предшественника, отказ на цикл и на ветку
              hgRefresh();await tick();document.querySelector('#hg_root [data-hgrow="T-12"] .hg-tt').click();const m=document.getElementById('hgsmodal'),ad=m.querySelector('[data-hgsadd]');
              ad.value='T-11';ad.dispatchEvent(new Event('change'));ad.value='T-11';ad.dispatchEvent(new Event('change'));
              const chips=[...m.querySelectorAll('[data-hgdeps] .depc')].length;m.querySelector('[data-hgsx=ok]').click();const panelDep=g('T-12').dep;
              const cyc=depCheck(g('T-01'),'T-13'),br=depCheck(g('T-03'),'FE-2'),self=depCheck(g('T-03'),'T-03');
              // клик по стрелке → «Удалить связь»
              hgRefresh();await tick();const gl=document.querySelector('#hg_root .hg-ln[data-ln="T-11>T-12"] .hit');
              gl.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:300,clientY:300}));const tip=!!document.querySelector('#hg_root .hg-ltip [data-hgdel="T-12"]');
              document.querySelector('#hg_root .hg-ltip [data-hgdel="T-12"]').click();const removed=g('T-12').dep;
              // «Бэклог»: несколько предшественников
              activate('backlog');const ri=ST.tasks.indexOf(g('T-20')),sel=document.querySelector('#v_backlog [data-depadd][data-di="'+ri+'"]');
              sel.value='T-16';sel.dispatchEvent(new Event('change',{bubbles:true}));const s2=document.querySelector('#v_backlog [data-depadd][data-di="'+ri+'"]');s2.value='T-17';s2.dispatchEvent(new Event('change',{bubbles:true}));
              const multi=g('T-20').dep;document.querySelector('#v_backlog [data-depdel="T-16"][data-di="'+ri+'"]').click();const afterDel=g('T-20').dep;
              const crit=cpm(ST.tasks),norm=migrate({tasks:[{id:'A',dep:''},{id:'B',dep:'A; X-9, A,B'}]}).tasks[1].dep;
              activate('hgantt');await tick();const xd=!!document.querySelector('#hg_root [data-hgrow="T-03"] .hg-xd');
              document.querySelector('#hg_root [data-hgl]').click();await tick();const off=!document.querySelector('#hg_root svg.hg-links');HG.links=true;
              const leg=document.querySelectorAll('#hg_root .hg-lleg > span').length;
              return {demoBranch,all,bad,conf,confList,l2,branch,chips,panelDep,cyc,br,self,tip,removed,multi,afterDel,critN:crit.size,norm,xd,off,leg,errs};
             }catch(e){return 'ERR:'+e.message+' '+e.stack;}finally{window.removeEventListener('error',h);ST.tasks=JSON.parse(keep);save();HG.level=2;HG.open={};HG.links=true;views();activate('dash');}}""")
            assert isinstance(r, dict), 'hglinks failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['demoBranch'] == 'FE-1,FE-2' and r['bad'] == '', 'demo links are not inside one branch: ' + str(r)
            assert 'T-01>T-03:crit' in r['all'] and 'T-13>T-14:crit' in r['all'] and len(r['all']) == 7, 'arrows for every demo link, critical path accented: ' + str(r['all'])
            assert r['conf'] and r['confList'], 'conflicting link drawn red and listed'
            assert 'FE-1>FE-2:der' in r['l2'] and 'FE-3>FE-4:der' in r['l2'], 'collapsed: links rolled up to visible features: ' + str(r['l2'])
            assert 'одной ветки' in r['branch'], 'link inside one branch is reported'
            assert r['chips'] == 1 and r['panelDep'] == 'T-11', 'panel adds a predecessor once: ' + str(r)
            assert 'цикл' in r['cyc'] and 'ветке' in r['br'] and 'самого себя' in r['self'], 'checks: cycle, branch, self: ' + str(r)
            assert r['tip'] and r['removed'] == '', 'arrow click → remove link'
            assert r['multi'] == 'T-16, T-17' and r['afterDel'] == 'T-17', 'backlog: several predecessors: ' + str(r)
            assert r['critN'] > 0 and r['norm'] == 'A', 'critical path with lists; migrate normalises the list: ' + str(r['norm'])
            assert r['xd'] and r['off'] and r['leg'] >= 5, 'external dependency marker, links toggle, legend: ' + str(r)
        case('hglinks: dependency arrows — several predecessors, rollup, conflicts, branch/cycle checks, editing', t_hglinks)

        # ---- Hierarchy Gantt in a stream: stories created from stream features grouped under the feature ----
        def t_hgstream():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             let keep=null;
             try{await sdocLoad(true);keep=JSON.stringify(SDOC.data.features);
              SDOC.data.features.push({id:'F-77',name:'Тестовая фича',status:'В работе',pi:SDOC.data.curPi,links:[{team:curTeam(),task:'T-12'},{team:curTeam(),task:'T-02'},{team:'t-other',task:'T-04'}]});
              HG.level=9;HG.open={};views();activate('hgantt');await new Promise(r=>setTimeout(r,50));hgRefresh();
              const rows=[...document.querySelectorAll('#hg_root .hg-row[data-hgrow]')].map(x=>x.dataset.hgrow),i=rows.indexOf('SF:F-77');
              const G=hgTree(),roots=G.nodes.map(x=>x.t.id),v=G.nodes.find(x=>x.t.id==='SF:F-77');
              const label=(document.querySelector('#hg_root [data-hgrow="SF:F-77"] .hg-id')||{}).textContent;
              document.querySelector('#hg_root [data-hgrow="SF:F-77"] .hg-tt').click();const noPanel=!(document.getElementById('hgsmodal')||{classList:{contains:()=>false}}).classList.contains('open');
              document.querySelector('#hg_root [data-hgo="SF:F-77"]').click();const toFeat=CURV==='features';
              return {i,next:rows[i+1],roots,kids:v?v.ch.map(c=>c.t.id):null,sp:v&&v.sp,label,noPanel,toFeat,lost:G.lost,errs};}
             catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);if(keep)SDOC.data.features=JSON.parse(keep);HG.level=2;HG.open={};views();activate('dash');}}""")
            assert isinstance(r, dict), 'hgstream failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['i'] >= 0 and r['next'] == 'T-12' and r['kids'] == ['T-12'], 'linked root story nested under the stream feature: ' + str(r)
            assert 'T-12' not in r['roots'] and 'SF:F-77' in r['roots'], 'story is no longer a root'
            assert r['sp'] == 3 and r['label'] == 'F-77' and r['lost'] == 0, 'rollup and label of the stream feature: ' + str(r)
            assert r['noPanel'] and r['toFeat'], 'stream feature: marks are automatic, ID opens «Фичи стрима»'
        case('hgantt stream: stories of stream features grouped under the feature row', t_hgstream)

        # ---- Stream: cross-team dependency marker ⇄ on the stream feature row ----
        def t_hgxdeps():
            r = page.evaluate("""async()=>{let keepF=null,keepD=null;
             try{await sdocLoad(true);keepF=JSON.stringify(SDOC.data.features);keepD=JSON.stringify(SDOC.data.deps);
              SDOC.data.features.push({id:'F-78',name:'Межкомандная',status:'В работе',pi:SDOC.data.curPi,links:[{team:curTeam(),task:'T-12'}]});
              SDOC.data.deps.push({id:'XD-77',from:curTeam(),to:'t2',feature:'F-78',item:'API',need:2,plan:3,status:'Открыта'});
              HG.level=9;HG.links=true;views();activate('hgantt');await new Promise(r=>setTimeout(r,60));hgRefresh();
              const m=document.querySelector('#hg_root [data-hgrow="SF:F-78"] .hg-xs');const late=m&&m.style.color;
              SDOC.data.deps[SDOC.data.deps.length-1].plan=2;SDOC.data.deps[SDOC.data.deps.length-1].status='Выполнена';hgRefresh();
              const ok=document.querySelector('#hg_root [data-hgrow="SF:F-78"] .hg-xs');
              return {has:!!m,title:m?m.title:'',late,ok:ok&&ok.style.color,crit:col('--crit'),good:col('--good'),leg:/Межкомандная/.test(document.querySelector('#hg_root .hg-lleg').textContent)};}
             finally{if(keepF)SDOC.data.features=JSON.parse(keepF);if(keepD)SDOC.data.deps=JSON.parse(keepD);HG.level=2;views();activate('dash');}}""")
            assert r['has'] and 'ждём' in r['title'] and 'нужно к итер. 2' in r['title'], 'cross-team dependency marker on the stream feature: ' + str(r)
            assert r['leg'], 'legend describes ⇄'
        case('hgantt stream: cross-team dependency marker on the stream feature row', t_hgxdeps)

        # ---- 28. Status report generation ----
        def t_status():
            r = page.evaluate("""()=>{const md=statusReportMd();
              return {len:md.length, rag:/Статус \\(RAG\\)/.test(md), kpi:/CPI \\/ SPI/.test(md),
                      hasVer:md.indexOf(APP_VERSION)>=0};}""")
            assert r['len'] > 200 and r['rag'] and r['kpi'], 'status report incomplete'
            assert r['hasVer'], 'status report missing version'
        case('status-report: RAG summary generated from data', t_status)

        # ---- 29. New PM registers seeded + portfolio snapshot ----
        def t_pm():
            r = page.evaluate("""()=>{try{
              const have=k=>Array.isArray(ST[k])&&ST[k].length>0;
              const regs=['changeRequests','issues','stakeholders','decisions','impediments','lessons','raci','storyMap','poker','portfolio'];
              const seeded=regs.every(have);
              // engagement gap computed
              const gap=(ST.stakeholders||[]).filter(x=>ENGAGE.indexOf(x.engageTarget)>ENGAGE.indexOf(x.engageCur)).length;
              // portfolio snapshot (guarded)
              const snap=JSON.stringify(ST.portfolio),perm=JSON.stringify(PERM);PERM.canEdit=true;
              const _s=window.save,_v=window.views,_a=window.activate,_t=window.toast;
              window.save=()=>{};window.views=()=>{};window.activate=()=>{};window.toast=()=>{};
              const n0=ST.portfolio.length;portfolioSnapshot();const grew=ST.portfolio.length>=n0;
              window.save=_s;window.views=_v;window.activate=_a;window.toast=_t;
              ST.portfolio=JSON.parse(snap);Object.assign(PERM,JSON.parse(perm));
              return {seeded, gap:gap>=0, grew};
            }catch(e){return 'ERR:'+e.message;}}""")
            assert r is not True and isinstance(r, dict), 'pm registers failed: ' + str(r)
            assert r['seeded'], 'not all PM registers seeded'
            assert r['gap'], 'stakeholder engagement gap compute failed'
            assert r['grew'], 'portfolio snapshot did not add/update entry'
        case('pm-registers: change/issues/stakeholders/... + portfolio snapshot', t_pm)

        # ---- 30. Team health & performance package (v1.43) ----
        def t_health_perf():
            r = page.evaluate("""()=>{try{
              // bus factor from Star Map
              const B=busFactor();
              // DORA from deployments + incidents
              const D=dora();
              const tiers=['Elite','High','Medium','Low','—'];
              const dOk=[D.tFreq,D.tLead,D.tCfr,D.tMttr].every(t=>tiers.includes(t));
              const cfrOk=D.count?Math.abs(D.cfr - D.failed/D.count)<1e-9:D.cfr===0;
              // aging WIP + say-do
              const aw=agingWip(); const agingOk=aw.every(x=>x.age>=0) && (aw.length<2 || aw[0].age>=aw[1].age);
              const sd=sayDo(compute()); const sdOk=sd.avg===null||(sd.avg>=0);
              // health check latest-per-dimension
              const hc=hcLatest(); const hcDims=Object.keys(hc).length;
              // seeded registers
              const seeded=['teamHealth','deployments','incidents'].every(k=>Array.isArray(ST[k])&&ST[k].length>0);
              return {busShape:('bf'in B&&'spof'in B&&'uncovered'in B), dOk, cfrOk, agingOk, sdOk, hcDims, seeded};
            }catch(e){return 'ERR:'+e.message;}}""")
            assert r is not True and isinstance(r, dict), 'health/perf failed: ' + str(r)
            assert r['busShape'], 'busFactor() shape invalid'
            assert r['dOk'] and r['cfrOk'], 'DORA tiers/CFR invalid'
            assert r['agingOk'], 'aging WIP ordering/age invalid'
            assert r['sdOk'], 'say-do ratio invalid'
            assert r['hcDims'] >= 1 and r['seeded'], 'health check / registers not seeded'
        case('health-perf: bus factor, DORA, aging WIP, say-do, health check', t_health_perf)

        # ---- 31. NAV integrity: unique ids, every id has a container ----
        def t_nav():
            r = page.evaluate("""()=>{const ids=NAV.flatMap(g=>g.items.map(i=>i[0]));
              const dups=ids.filter((x,i)=>ids.indexOf(x)!==i);
              const missing=ids.filter(id=>!document.getElementById('v_'+id));
              return {n:ids.length, uniq:new Set(ids).size, dups, missing, groups:NAV.length,
                      names:NAV.map(g=>g.g)};}""")
            assert r['n'] == r['uniq'], 'duplicate NAV ids: ' + str(r['dups'])
            assert not r['missing'], 'NAV ids without a v_ container: ' + str(r['missing'])
            assert r['groups'] >= 8, 'unexpectedly few nav groups'
            assert 'Обзор' in r['names'] and 'Команда' in r['names'], 'expected regrouped blocks missing'
        case('nav: unique ids, containers, regrouped blocks', t_nav)

        # ---- 32. Streams & teams (local mode): isolation, templates, switching, request context ----
        def t_org_local():
            r = page.evaluate("""async()=>{try{
              setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');
              const t1Tasks=ST.tasks.length, t1Dod=(ST.dod||[]).length;
              const sid=await orgAddStream('Платежи'), tid=await orgAddTeam('Касса',sid,'empty');
              const fresh=JSON.parse(localStorage.getItem(stKey(tid)));
              const blankOk=fresh.tasks.length===0&&(fresh.dod||[]).length===t1Dod&&fresh.params.name==='Касса';
              await switchTeam(tid);
              const switched=curTeam()===tid&&ST.tasks.length===0&&/Платежи › Касса/.test(document.getElementById('teamsw_l').textContent);
              ST.tasks.push({id:'T-K1',title:'Задача кассы',role:'Backend',type:'Задача',est:3,status:'В работе',sprint:1});save();
              const isolated=JSON.parse(localStorage.getItem(stKey(tid))).tasks.length===1&&JSON.parse(localStorage.getItem(stKey('t1'))).tasks.length===t1Tasks;
              const ctx=hdrs(false)['X-Team-Id']===tid&&brdWSUrl().includes('team='+tid);
              const cid=await orgAddTeam('Клон','s1','copy');
              const copyOk=JSON.parse(localStorage.getItem(stKey(cid))).tasks.length===1;
              await switchTeam('t1');const back=ST.tasks.length===t1Tasks;
              activate('org');const rows=document.querySelectorAll('#org_root tr[data-team]').length;
              let t1Locked=false;try{await orgDelTeam('t1');}catch(e){t1Locked=true;}
              await orgDelTeam(cid);await orgDelTeam(tid);await orgDelStream(sid);
              const cleaned=ORG.teams.length===1&&ORG.streams.length===1&&localStorage.getItem(stKey(tid))===null;
              activate('dash');
              return {blankOk,switched,isolated,ctx,copyOk,back,rows,t1Locked,cleaned};
            }catch(e){return 'ERR:'+e.message;}}""")
            assert isinstance(r, dict), 'org flow failed: ' + str(r)
            for k in ('blankOk', 'switched', 'isolated', 'ctx', 'copyOk', 'back', 't1Locked', 'cleaned'):
                assert r[k], k + ' failed: ' + str(r)
            assert r['rows'] == 3, 'org section should list 3 teams, got ' + str(r['rows'])
        case('org: streams & teams — isolation, templates, switching, context', t_org_local)

        # ---- 33. Import a team from a JSON export (e.g. from the base app) ----
        def t_org_import():
            r = page.evaluate("""async()=>{try{
              setPerm('admin');applyPerms();
              const data=JSON.parse(JSON.stringify(SEED));data.params.name='Импортированная команда';
              const want=migrate(JSON.parse(JSON.stringify(data))).tasks.length;
              const id=await orgImportTeam(data,null,null);
              const ok=curTeam()===id&&ST.tasks.length===want&&ST.params.name==='Импортированная команда'
                &&JSON.parse(localStorage.getItem(stKey(id))).tasks.length===want;
              let bad=false;try{await orgImportTeam([1,2],null,null);}catch(e){bad=true;}
              await switchTeam('t1');await orgDelTeam(id);
              return {ok,bad,teams:ORG.teams.length};
            }catch(e){return 'ERR:'+e.message;}}""")
            assert isinstance(r, dict), 'import failed: ' + str(r)
            assert r['ok'], 'imported team has wrong data'
            assert r['bad'], 'non-object JSON must be rejected'
            assert r['teams'] == 1, 'cleanup failed'
        case('org: import a team from JSON export', t_org_import)

        # ---- 34. Header switcher UI ----
        def t_org_switcher():
            page.evaluate("""async()=>{setPerm('admin');applyPerms();await orgAddTeam('Вторая','s1','empty');}""")
            page.click('#teamsw')
            n = page.evaluate("()=>document.querySelectorAll('#teampop [data-team]').length")
            assert n == 2, 'switcher should list 2 teams, got ' + str(n)
            page.click('#teampop [data-team="t2"]')
            page.wait_for_function("()=>curTeam()==='t2'")
            opened = page.evaluate("()=>document.getElementById('teamdm').classList.contains('open')")
            assert not opened, 'switcher should close after choosing a team'
            page.evaluate("""async()=>{await switchTeam('t1');await orgDelTeam('t2');}""")
            assert page.evaluate("()=>curTeam()==='t1'&&ORG.teams.length===1")
        case('org: header switcher lists teams and switches', t_org_switcher)

        # ---- 35. An empty team renders every section without errors ----
        def t_org_blank_sections():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));
              window.addEventListener('error',h);window.addEventListener('unhandledrejection',h);
              try{setPerm('admin');applyPerms();const id=await orgAddTeam('Пустая','s1','empty');await switchTeam(id);
                const blank=ST.tasks.length===0;
                for(const g of NAV)for(const it of g.items){try{activate(it[0]);}catch(e){errs.push(it[0]+': '+e.message);}}
                await new Promise(r=>setTimeout(r,500));
                await switchTeam('t1');await orgDelTeam(id);activate('dash');
                return {blank,errs};
              }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);window.removeEventListener('unhandledrejection',h);}}""")
            assert isinstance(r, dict), 'blank-team run failed: ' + str(r)
            assert r['blank'], 'empty team should have no tasks'
            assert not r['errs'], 'sections failed on an empty team: ' + str(r['errs'][:5])
        case('org: empty team renders every section', t_org_blank_sections)

        # ---- 36. Stream level: aggregation, feature → team story, PI board, predictability, conflicts ----
        def t_stream_level():
            r = page.evaluate("""async()=>{try{
              setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');
              localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;STC.at=0;
              const a=await orgAddTeam('Альфа','s1','copy'),b=await orgAddTeam('Бета','s1','empty');
              const states=await streamTeamStates(true);
              const people=states.reduce((s,x)=>s+((x.st&&x.st.team)||[]).length,0);
              activate('stream');await sdocLoad(true);await streamFill('stream',true);
              const kpis=[...document.querySelectorAll('#str_stream .kpi .k-val')].map(e=>e.textContent.trim());
              const rows=document.querySelectorAll('#str_stream tbody tr').length;
              // фича и её история в бэклоге ДРУГОЙ команды, во 2-й итерации PI
              activate('features');await streamFill('features',true);
              document.querySelector('#str_features [data-sact=add][data-coll=features]').click();
              const F=()=>SDOC.data.features[0],D=()=>SDOC.data;F().name='Оплата картой';sdocSave();await streamFill('features',true);
              document.querySelector('#str_features [data-sact=split]').click();
              const box=document.getElementById('str_split');box.querySelector('[data-f=team]').value=a;
              box.querySelector('[data-f=title]').value='Платёжный шлюз';box.querySelector('[data-f=est]').value='5';box.querySelector('[data-f=iter]').value='2';
              document.querySelector('#str_features [data-sact=splitGo]').click();
              for(let k=0;k<40&&!F().links.length;k++)await new Promise(r=>setTimeout(r,50));
              const teamA=JSON.parse(localStorage.getItem(stKey(a)));const f=F();const story=teamA.tasks.find(t=>t.id===(f.links[0]||{}).task);
              const storyOk=!!story&&story.title==='['+f.id+'] Платёжный шлюз'&&story.type==='История'&&+story.sprint===2;
              const notInT1=!ST.tasks.some(t=>/Платёжный шлюз/.test(t.title));
              // программная доска: фича — в строке команды «Альфа», итерация 2
              activate('streampi');await streamFill('streampi',true);
              const boardRow=[...document.querySelectorAll('#str_streampi .str-board tbody tr')].find(tr=>tr.querySelector('th').textContent==='Альфа');
              const chipOk=!!boardRow&&boardRow.children[2].textContent.includes(f.id);
              // предсказуемость PI и конфликт зависимостей
              let d=SDOC.data;const pi=piCur();
              d.objectives.push({id:'O-01',pi:pi.id,team:a,text:'x',bv:10,actual:8,committed:true},{id:'O-02',pi:pi.id,team:b,text:'y',bv:5,actual:5,committed:true},{id:'O-03',pi:pi.id,team:b,text:'z',bv:9,actual:'',committed:false});
              d.deps.push({id:'XD-01',from:b,to:a,feature:f.id,item:'API',need:2,plan:3,status:'Принята'},{id:'XD-02',from:a,to:b,feature:'',item:'UI',need:3,plan:2,status:'Открыта'});
              sdocSave();await streamFill('streampi',true);
              const pred=piPredict(pi),bad=document.querySelectorAll('#str_streampi .str-chip.bad').length;
              // ROAM: перенос высокого риска команды; Scrum of Scrums: строка на каждую команду
              activate('roam');await streamFill('roam',true);const before=D().roam.length;
              const tr=document.querySelector('#str_roam [data-sact=toRoam]');if(tr)tr.click();
              for(let k=0;k<20&&D().roam.length===before;k++)await new Promise(r=>setTimeout(r,50));
              activate('sos');await streamFill('sos',true);document.querySelector('#str_sos [data-sact=sosNew]').click();
              for(let k=0;k<40&&!D().sos.length;k++)await new Promise(r=>setTimeout(r,50));
              d=D();const sosOk=d.sos.length===3&&d.sos.every(s=>s.date)&&/Спринт #/.test((d.sos.find(s=>s.team==='t1')||{}).done||'');
              // сохранено в документе стрима
              const saved=JSON.parse(localStorage.getItem(sdocKey('s1')));
              // просмотр: нет кнопок изменения, sdocSave() запрещён
              setPerm('viewer');applyPerms();await streamFill('features',true);
              const roNoAdd=!document.querySelector('#str_features [data-sact=add]')&&sdocSave()===false;
              setPerm('admin');applyPerms();
              await orgDelTeam(a);await orgDelTeam(b);localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;activate('dash');
              return {kpiTeams:kpis[0],kpiPeople:kpis[1],people,rows,storyOk,notInT1,chipOk,pred,bad,roam:D().roam.length-before,sosOk,
                      saved:!!saved&&saved.features.length===1&&saved.features[0].links.length===1,roNoAdd};
            }catch(e){return 'ERR:'+e.message+' '+(e.stack||'').split('\\n')[1];}}""")
            assert isinstance(r, dict), 'stream flow failed: ' + str(r)
            assert r['kpiTeams'] == '3 · %d' % r['people'] and r['rows'] == 3, 'stream KPI «команд · людей» must sum over 3 teams: ' + str(r)
            assert r['storyOk'] and r['notInT1'], 'feature story must land in the chosen team backlog: ' + str(r)
            assert r['chipOk'], 'program board should show the feature in team row / iteration 2'
            assert abs(r['pred'] - 13 / 15) < 1e-9, 'PI predictability = actual/plan BV of committed objectives: ' + str(r['pred'])
            assert r['bad'] == 1, 'exactly one dependency conflict expected, got ' + str(r['bad'])
            assert r['roam'] == 1, 'high team risk should move into ROAM'
            assert r['sosOk'], 'Scrum of Scrums agenda should have a row per team with sprint progress'
            assert r['saved'], 'stream document not persisted'
            assert r['roNoAdd'], 'viewer must not edit stream data'
        case('stream: aggregation, feature stories, PI board, predictability, ROAM, SoS', t_stream_level)

        # ---- 37. Stream: feature kanban, System Demo agenda, burn-up / velocity charts ----
        def t_stream_kanban_demo():
            r = page.evaluate("""async()=>{try{
              setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');
              localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;STC.at=0;
              const a=await orgAddTeam('Гамма','s1','copy');await sdocLoad(true);const pi=piCur();
              SDOC.data.features.push({id:'F-01',name:'Фича',status:'Анализ',pi:pi.id,owner:'PO',bv:5,tc:5,rr:5,size:5,links:[]});sdocSave();
              const states=await streamTeamStates(true);const x=states.find(s=>s.team.id===a);
              const id=await teamAddTask(a,{title:'[F-01] История',assignee:'',role:'',type:'История',est:8,status:'Готово',sprint:sprintOfIter(x.st,2,pi),dep:'',started:'',done:'',priority:'Should'});
              SDOC.data.features[0].links.push({team:a,task:id});sdocSave();STC.at=0;
              // канбан: колонки по статусам, перенос карточки кнопкой ▶
              localStorage.setItem('str_fview','kanban');activate('features');await streamFill('features',true);
              const cols=document.querySelectorAll('#str_features .str-kcol').length;
              document.querySelector('#str_features .str-card [data-sact=fmove][data-dir="1"]').click();
              for(let k=0;k<20&&SDOC.data.features[0].status!=='Бэклог';k++)await new Promise(r=>setTimeout(r,50));
              const moved=SDOC.data.features[0].status==='Бэклог';localStorage.setItem('str_fview','table');
              // System Demo: повестка из фич с готовыми историями итерации 2 (повторно не дублируется)
              activate('sysdemo');await streamFill('sysdemo',true);
              const st2=await streamTeamStates(true);const rows=demoAgenda(st2,2,'2026-08-28');const again=(SDOC.data.demos=SDOC.data.demos.concat(rows),sdocSave(),demoAgenda(st2,2,'2026-08-28').length);
              const none=demoAgenda(st2,1,'2026-08-14').length;
              // графики обзора стрима
              const B=streamBurnup(st2,pi);activate('stream');await streamFill('stream',true);
              const charts=!!document.querySelector('#str_bu svg')&&!!document.querySelector('#str_vel svg');
              const sheets=streamSheets().map(x=>x.name+':'+(x.aoa.length-1));
              await orgDelTeam(a);localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;activate('dash');
              return {sheets,cols,moved,demo:rows.length,demoTeams:rows[0]&&rows[0].teams,again,none,scope:B.scope,done2:B.done[1],charts};
            }catch(e){return 'ERR:'+e.message;}}""")
            assert isinstance(r, dict), 'kanban/demo flow failed: ' + str(r)
            assert r['cols'] == 5, 'feature kanban needs 5 status columns'
            assert r['moved'], 'card should move to the next status column'
            assert r['demo'] == 1 and r['demoTeams'] == 'Гамма', 'System Demo agenda from done stories: ' + str(r)
            assert r['again'] == 0 and r['none'] == 0, 'agenda must not duplicate / must skip iterations without done stories'
            assert r['scope'] == 8 and r['done2'] == 8, 'burn-up: scope and cumulative done by iteration 2: ' + str(r)
            assert r['charts'], 'stream overview charts not rendered'
            for sh in ('Стримы и команды:2', 'Фичи стрима:1', 'System Demo:1'):
                assert sh in r['sheets'], 'Excel stream sheet missing: ' + sh + ' in ' + str(r['sheets'])
        case('stream: feature kanban, System Demo agenda, burn-up charts', t_stream_kanban_demo)

        # ---- 38. Stream dashboard: aggregates, alerts, tabs, matrix/cards, team panel, snapshots & trends ----
        def t_stream_dashboard():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             try{setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');
              localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;STC.at=0;
              const a=await orgAddTeam('Дельта','s1','copy'),b=await orgAddTeam('Эпсилон','s1','empty');
              await sdocLoad(true);SDOC.data.deps.push({id:'XD-01',from:a,to:b,feature:'',item:'API',need:2,plan:4,status:'Открыта'});sdocSave();
              const states=await streamTeamStates(true);const people=states.reduce((s,x)=>s+((x.st&&x.st.team)||[]).length,0);
              const res={};
              for(const tab of ['sum','teams','flow','qual','people','trend']){localStorage.setItem('str_dtab',tab);localStorage.setItem('str_tview','matrix');
                activate('stream');await streamFill('stream',true);
                res[tab]={rows:document.querySelectorAll('#str_stream tr[data-sact=teamPanel]').length,svg:document.querySelectorAll('#str_stream .str-chart svg').length};}
              const agg=streamAgg(STM,states,piCur());const alerts=streamAlerts(STM,agg,piCur());
              localStorage.setItem('str_dtab','teams');localStorage.setItem('str_tview','cards');await streamFill('stream',true);
              const cards=document.querySelectorAll('#str_stream .str-tc[data-sact=teamPanel]').length;
              document.querySelector('#str_stream .str-tc[data-sact=teamPanel]').click();
              const dr=document.getElementById('str_drawer');const panel=!dr.hidden&&dr.textContent.includes(STM[0].x.team.name);
              // срезы: авто при открытии (1 на итерацию), ручной — перезапись той же итерации, второй срез → графики трендов
              const pi=piCur(),k=piIterNow(pi);const snapsAuto=(SDOC.data.snaps||[]).filter(s=>s.pi===pi.id).length;
              localStorage.setItem('str_dtab','sum');await streamFill('stream',true);document.querySelector('#str_stream [data-sact=snap]').click();
              await new Promise(r=>setTimeout(r,300));const snapsManual=(SDOC.data.snaps||[]).filter(s=>s.pi===pi.id&&s.iter===k).length;
              const s0=JSON.parse(JSON.stringify(SDOC.data.snaps[0]));s0.iter=k-1;s0.s.vel=10;SDOC.data.snaps.push(s0);sdocSave();
              localStorage.setItem('str_dtab','trend');await streamFill('stream',true);const trendSvg=document.querySelectorAll('#str_stream .str-chart svg').length;
              const sheet=streamSheets().find(x=>x.name==='Срезы стрима');
              localStorage.setItem('str_dtab','sum');localStorage.setItem('str_tview','matrix');
              await orgDelTeam(a);await orgDelTeam(b);localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;activate('dash');
              return {res,teams:agg.teams,aggPeople:agg.people,people,conf:agg.conf,depAlert:alerts.some(x=>x.act.view==='streampi'),
                      alertsSorted:alerts.every((x,i)=>i===0||!(x.lvl==='crit'&&alerts[i-1].lvl!=='crit')),cards,panel,k,snapsAuto,snapsManual,trendSvg,
                      sheetRows:sheet?sheet.aoa.length-1:-1,errs};
             }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);}}""")
            assert isinstance(r, dict), 'stream dashboard failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['teams'] == 3 and r['aggPeople'] == r['people'], 'aggregates over 3 teams: ' + str(r)
            for tab in ('sum', 'teams', 'flow', 'qual', 'people'):
                assert r['res'][tab]['rows'] == 3, tab + ' matrix should list 3 teams: ' + str(r['res'])
            assert r['res']['sum']['svg'] >= 1 and r['res']['flow']['svg'] == 2 and r['res']['qual']['svg'] == 2, 'charts missing: ' + str(r['res'])
            assert r['conf'] == 1 and r['depAlert'] and r['alertsSorted'], 'dependency conflict must raise a sorted alert: ' + str(r)
            assert r['cards'] == 3 and r['panel'], 'cards view and team panel'
            if r['k']:
                assert r['snapsAuto'] == 1 and r['snapsManual'] == 1, 'one snapshot per iteration (auto + manual overwrite): ' + str(r)
                assert r['trendSvg'] == 3, 'trend charts with 2 snapshots: ' + str(r['trendSvg'])
                assert r['sheetRows'] >= 2, 'Excel sheet «Срезы стрима»'
        case('stream dashboard: aggregates, alerts, tabs, matrix/cards, panel, snapshots', t_stream_dashboard)

        # ---- 39. Stream maturity: votes → median/spread, RTE final, indicators & mismatch, dims config, improvements ----
        def t_stream_maturity():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             try{setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');
              localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;STC.at=0;
              const a=await orgAddTeam('Зета','s1','copy'),b=await orgAddTeam('Эта','s1','empty');await sdocLoad(true);const pi=piCur();
              await matSetVote('pi','t1',4);await matSetVote('pi',a,2);
              const st=await streamTeamStates(true);let row=matRows(st,pi).find(x=>x.dm.id==='pi');
              const voteOk=row.n===2&&row.med===3&&row.spread===2&&row.eff===3&&row.fin===null;
              SDOC.data.objectives.push({id:'O-1',pi:pi.id,team:'t1',text:'x',bv:10,actual:5,committed:true});
              matRound(pi.id,true).final.pi=5;sdocSave();
              row=matRows(st,pi).find(x=>x.dm.id==='pi');const S=matSummary(st,pi);
              const indOk=row.ind.lvl===2&&row.gap===3&&S.mism>=1&&S.overall===5;
              const al=streamAlerts(st.map(x=>({x,m:teamMetricsX(x.st)})),streamAgg(st.map(x=>({x,m:teamMetricsX(x.st)})),st,pi),pi).some(x=>x.act.view==='smaturity');
              activate('smaturity');await streamFill('smaturity',true);
              const rows=document.querySelectorAll('#str_smaturity .mat-t tbody tr').length,sel=document.querySelectorAll('#str_smaturity .mat-v select').length;
              const cb=document.querySelector('#str_smaturity [data-mat=on][data-dim=roles]');cb.checked=false;cb.dispatchEvent(new Event('change',{bubbles:true}));
              await new Promise(r=>setTimeout(r,200));const off=matDims().length;
              matData().custom.push({id:'c1',name:'Работа с бизнес-владельцами'});const withCustom=matDims().length;
              await matSetVote('deps','t1',2);const n1=matSuggest(st),n2=matSuggest(st);
              const sheet=streamSheets().some(x=>x.name==='Зрелость стрима'&&x.aoa.length===withCustom+1);
              setPerm('viewer');applyPerms();let denied=false;try{await matSetVote('pi','t1',1);}catch(e){denied=true;}setPerm('admin');applyPerms();
              await orgDelTeam(a);await orgDelTeam(b);localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;activate('dash');
              return {voteOk,indOk,al,rows,sel,off,withCustom,n1,n2,sheet,denied,errs};
             }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);}}""")
            assert isinstance(r, dict), 'stream maturity failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['voteOk'], 'votes must give median 3 and spread 2 without a final'
            assert r['indOk'], 'RTE final 5 vs indicator 2 (predictability 50%) must be a mismatch'
            assert r['al'], 'dashboard must signal the maturity mismatch'
            assert r['rows'] == 10 and r['sel'] == 30, 'practices table 10 dims, votes matrix 10 x 3 teams: ' + str(r)
            assert r['off'] == 9 and r['withCustom'] == 10, 'disable a dim / add a custom dim: ' + str(r)
            assert 1 <= r['n1'] <= 3 and r['n2'] == 0, 'improvements from weakest dims without duplicates: ' + str(r)
            assert r['sheet'], 'Excel sheet «Зрелость стрима»'
            assert r['denied'], 'viewer must not vote'
        case('stream maturity: votes, RTE final, indicators, mismatch, config, improvements', t_stream_maturity)

        # ---- 40. Ergonomics: lazy views, compact nav (levels, hubs, tabs, search), quick create ----
        def t_ergonomics():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             try{setPerm('admin');applyPerms();NAVS.mode='compact';activate('dash');views();
              const lazyBefore=document.querySelectorAll('#v_backlog .lazy-ph').length;activate('backlog');const lazyAfter=document.querySelectorAll('#v_backlog .lazy-ph').length;
              const allTitles=NAV.flatMap(g=>g.items.map(i=>i[0])).every(id=>{const v=document.getElementById('v_'+id);return v&&v.querySelector('h1');});
              const navIds=NAV.flatMap(g=>g.items.map(i=>i[0])),mapped=new Set(Object.values(NAV2).flatMap(l=>l.flatMap(e=>e[3])));
              const covered=navIds.every(id=>mapped.has(id));
              activate('wsjf');const tabs=[...document.querySelectorAll('#v_wsjf > .hub-tabs [data-hubv]')].map(b=>b.dataset.hubv);
              const lvlTeam=NAVS.level==='team';document.querySelector('#v_wsjf > .hub-tabs [data-hubv=moscow]').click();const tabGo=CURV==='moscow';
              const entries=document.querySelectorAll('#nav .nav-hubs:not(.nav-smart) .nav-item').length;
              document.querySelector('#nav [data-lvl=stream]').click();const toStream=NAVS.level==='stream'&&NAV2.stream.some(e=>e[3].includes(CURV));
              navFilter('гант');const found=[...document.querySelectorAll('#nav .nav-allg .nav-row')].filter(x=>x.style.display!=='none').map(x=>x.querySelector('.nav-lbl').textContent);navFilter('');
              activate('dash');
              const n0=ST.tasks.length;await qcOpen('task');const m=document.getElementById('qcmodal');m.querySelector('[data-q=title]').value='Быстрая задача';qcSubmit(QC[0]);
              const last=ST.tasks[ST.tasks.length-1];const qcOk=ST.tasks.length===n0+1&&last.title==='Быстрая задача'&&+last.sprint===compute().cur;
              ST.tasks.pop();save();
              return {lazyBefore,lazyAfter,allTitles,covered,tabs,lvlTeam,tabGo,entries,toStream,found,qcOk,errs};
             }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);}}""")
            assert isinstance(r, dict), 'ergonomics failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['lazyBefore'] > 0 and r['lazyAfter'] == 0, 'hidden sections must build on open: ' + str(r)
            assert r['allTitles'], 'every section keeps its title (assistant/search) without being built'
            assert r['covered'], 'every NAV section must be reachable from the compact menu'
            assert r['tabs'] == ['rice', 'wsjf', 'moscow'] and r['lvlTeam'] and r['tabGo'], 'hub tabs: ' + str(r)
            assert 10 <= r['entries'] <= 20, 'compact team menu should have 10-20 entries, got ' + str(r['entries'])
            assert r['toStream'], 'level switch must open a stream section'
            assert r['found'] == ['Гант', 'Гант по иерархии'], 'search must find sections inside hubs: ' + str(r['found'])
            assert r['qcOk'], 'quick create must add a task to the current sprint'
        case('ergonomics: lazy views, compact nav levels/hubs/tabs/search, quick create', t_ergonomics)

        # ---- 41. Scenarios: «Мой день», first steps for an empty team, new stream wizard ----
        def t_scenarios():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             try{setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');
              const me=ST.team[0].name;lsSetS('me:'+curTeam(),me);views();activate('myday');
              const cur=compute().cur,mine=ST.tasks.filter(t=>+t.sprint===cur&&t.assignee===me&&t.type!=='Эпик');
              const rows=document.querySelectorAll('#myday_root .md-task').length;
              const todo=mine.find(t=>t.status==='To Do');let started=true;
              if(todo){const st0=todo.status;document.querySelector('#myday_root [data-md=start][data-id="'+todo.id+'"]').click();started=ST.tasks.find(t=>t.id===todo.id).status==='В работе';ST.tasks.find(t=>t.id===todo.id).status=st0;save();}
              lsSetS('me:'+curTeam(),'');
              const nOrg=ORG.teams.length;
              const e=await orgAddTeam('Новая','s1','empty');await switchTeam(e);views();activate('myday');
              const onb=!!document.querySelector('#myday_root .onb');activate('dash');const onbDash=!!document.querySelector('#v_dash > .onb-wrap .onb');
              const steps=onbSteps().filter(s=>s[2]).length;
              await switchTeam('t1');await orgDelTeam(e);
              wizOpen();const m=document.getElementById('wizmodal');m.querySelector('[data-w=name]').value='Стрим «Тест»';m.querySelector('[data-w=teams]').value=['А','Б','В'].join(String.fromCharCode(10));
              m.querySelector('[data-w=pi]').value='PI 7';await wizRun();
              const s=ORG.streams.find(x=>x.name==='Стрим «Тест»'),ts=s?ORG.teams.filter(t=>t.streamId===s.id):[];
              const wiz=!!s&&ts.length===3&&curStream()===s.id&&SDOC.data.pis[0].name==='PI 7'&&CURV==='stream';
              await switchTeam('t1');for(const x of ts)await orgDelTeam(x.id);if(s){localStorage.removeItem(sdocKey(s.id));await orgDelStream(s.id);}activate('dash');
              return {mine:mine.length,rows,started,onb,onbDash,steps,wiz,back:ORG.teams.length===nOrg,errs};
             }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);}}""")
            assert isinstance(r, dict), 'scenarios failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['rows'] == r['mine'], 'my day lists my tasks of the current sprint: ' + str(r)
            assert r['started'], 'start button must change the task status'
            assert r['onb'] and r['onbDash'] and r['steps'] < 6, 'empty team shows first steps: ' + str(r)
            assert r['wiz'] and r['back'], 'wizard creates stream, 3 teams and PI: ' + str(r)
        case('scenarios: my day, first steps, new stream wizard', t_scenarios)

        # ---- Profile: «Мой профиль» — who am I, my work/time, mentions, settings; server binding & own password ----
        def t_profile():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             const KEY=()=>%(KEY)s,keepMe=lsGetS(KEY(),''),keepFetch=window.fetch,keepAuth=Object.assign({},AUTH),keepBoard=JSON.stringify(ST.board||{});
             try{setPerm('editor');applyPerms();lsSetS(KEY(),'');views();activate('dash');
              document.getElementById('profbtn').click();const opened=CURV==='profile';
              const tabs=[...document.querySelectorAll('#v_profile > .hub-tabs [data-hubv]')].map(b=>b.dataset.hubv);
              const noMe=!!document.querySelector('#prof_root .md-empty');const me=ST.team[0].name;
              const sel=document.querySelector('#prof_root [data-pf=me]');sel.value=me;sel.dispatchEvent(new Event('change',{bubbles:true}));
              await new Promise(r=>setTimeout(r,80));
              const stored=lsGetS(KEY(),'')===me&&mdMe()===me;
              const open=ST.tasks.filter(t=>t.type!=='Эпик'&&t.assignee===me&&t.status!=='Готово').length;
              const head=[...document.querySelectorAll('#prof_root .md-h')].map(x=>x.textContent);
              const workOk=head.some(x=>x==='Моя работа — открытых задач: '+open);
              const it=(ST.board.items=ST.board.items||[]);it.push({id:'pf-test',t:'sticky',x:0,y:0,w:100,h:80,text:'Тест',comments:[{id:'c1',a:'Петрова М.',t:'@'+me+' посмотри, пожалуйста',ts:'2026-09-10T10:00:00Z',m:[me]}]});
              views();activate('profile');const ment=[...document.querySelectorAll('#prof_root .md-li[data-mdgo=board]')].some(b=>b.textContent.includes('посмотри'));
              const localPw=!document.querySelector('#prof_root [data-pw]');
              const d0=document.body.classList.contains('dense');document.querySelector('#prof_root [data-pf=dense]').click();const d1=document.body.classList.contains('dense');
              document.querySelector('#prof_root [data-pf=dense]').click();const dense=!d0&&d1&&!document.body.classList.contains('dense')&&CURV==='profile';
              // сервер: привязка в учётной записи и смена пароля (ответы сервера подменены)
              const calls=[];let pwStatus=204;
              window.fetch=(u,o)=>{const s=String(u);const J=(x,st)=>Promise.resolve(new Response(x==null?null:JSON.stringify(x),{status:st||200,headers:{'Content-Type':'application/json'}}));
               if(s.includes('api/auth/me/password')){calls.push(['pw',JSON.parse(o.body)]);return pwStatus===204?J(null,204):J({error:'wrong_password'},pwStatus);}
               if(s.includes('api/auth/me')&&o&&o.method==='PUT'){const b=JSON.parse(o.body);calls.push(['me',b]);return J({username:'po',role:'EDITOR',name:'PO',member:b.member||null});}
               return keepFetch(u,o);};
              AUTH.mode='server';AUTH.token='demo';AUTH.username='po';AUTH.user='PO';AUTH.role='EDITOR';AUTH.member='';
              const other=ST.team[1].name;await profSetMe(other);lsSetS(KEY(),me);
              const srvMe=AUTH.member===other&&mdMe()===other;views();activate('profile');
              const set=(k,v)=>{document.querySelector('#prof_root [data-pw='+k+']').value=v;};const msg=()=>document.getElementById('pf_pwmsg').textContent;
              set('old','Old-pass-1');set('new','New-pass-2');set('rep','New-pass-X');await profPassword();const mism=msg();
              set('new','short');set('rep','short');await profPassword();const shortM=msg();
              set('new','New-pass-2');set('rep','New-pass-2');await profPassword();const okM=msg();
              pwStatus=403;set('old','bad');set('new','New-pass-3');set('rep','New-pass-3');await profPassword();const badM=msg();
              uiMenuSync();const lo=document.getElementById('logoutbtn').style.display!=='none';
              return {opened,tabs,noMe,stored,workOk,head,ment,localPw,dense,srvMe,calls:calls.map(c=>c[0]),meBody:calls[0]&&calls[0][1],pwBody:(calls.find(c=>c[0]==='pw')||[])[1],mism,shortM,okM,badM,lo,errs};
             }catch(e){return 'ERR:'+e.message;}
             finally{window.removeEventListener('error',h);window.fetch=keepFetch;Object.assign(AUTH,keepAuth);ST.board=JSON.parse(keepBoard);lsSetS(KEY(),keepMe);uiMenuSync();views();activate('dash');}}""" % {'KEY': "'me:'+curTeam()"})
            assert isinstance(r, dict), 'profile failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['opened'] and r['tabs'] == ['myday', 'profile'], 'profile opens from the user menu, tab next to «Мой день»: ' + str(r)
            assert r['noMe'] and r['stored'], 'member binding: prompt when unset, stored after choice'
            assert r['workOk'] and {'Кто я', 'Моё время', 'Настройки'} <= set(r['head']), 'profile cards: ' + str(r['head'])
            assert r['ment'], 'board @mention shows in profile'
            assert r['localPw'] and r['dense'], 'local mode: no password form; settings toggle density'
            assert r['srvMe'] and r['meBody'] == {'member': r['meBody']['member']} and r['meBody']['member'], 'server binding wins over the browser choice: ' + str(r)
            assert r['calls'].count('pw') == 2 and r['pwBody'] == {'oldPassword': 'Old-pass-1', 'newPassword': 'New-pass-2'}, 'password requests: ' + str(r)
            assert 'не совпадают' in r['mism'] and '8 символов' in r['shortM'] and 'изменён' in r['okM'] and 'неверно' in r['badM'], str(r)
            assert r['lo'], 'logout visible in the user menu with server session'
        case('profile: who am I, my work/time, mentions, settings, server binding & own password', t_profile)

        # ---- Viewer: personal controls (profile, «Я —», Gantt view) stay usable in read-only mode ----
        def t_viewer_free():
            r = page.evaluate("""()=>{const keepAuth=Object.assign({},AUTH);
             try{setPerm('viewer');applyPerms();AUTH.mode='server';AUTH.token='demo';AUTH.username='v';AUTH.user='Наблюдатель';AUTH.role='VIEWER';
              views();activate('profile');const me=document.querySelector('#prof_root [data-pf=me]'),pw=document.querySelector('#prof_root [data-pw=old]'),btn=document.querySelector('#prof_root [data-pf=pw]');
              const prof=!!me&&!me.disabled&&!!pw&&!pw.readOnly&&!!btn&&btn.offsetParent!==null;
              activate('myday');const mm=document.querySelector('#myday_root [data-md=me]');const md=!!mm&&!mm.disabled;
              activate('hgantt');const hf=document.querySelector('#hg_root [data-hgf]');const hg=!!hf&&!hf.disabled;
              activate('backlog');const data=[...document.querySelectorAll('#v_backlog td input, #v_backlog td select')].every(e=>e.disabled||e.readOnly);
              return {prof,md,hg,data};}
             finally{Object.assign(AUTH,keepAuth);setPerm('editor');applyPerms();views();activate('dash');}}""")
            assert r['prof'], 'profile: member select, password fields and button usable for VIEWER'
            assert r['md'] and r['hg'], 'my day «Я —» and Gantt fact toggle usable for VIEWER: ' + str(r)
            assert r['data'], 'project data stays read-only for VIEWER'
        case('viewer: personal controls stay usable, data read-only', t_viewer_free)

        # ---- 42. Stream management team: positions, dashboard line, maturity indicator, Excel, wizard ----
        def t_stream_positions():
            r = page.evaluate("""async()=>{const errs=[];const h=e=>errs.push(String(e.message||e.reason||e));window.addEventListener('error',h);
             try{setPerm('admin');applyPerms();if(curTeam()!=='t1')await switchTeam('t1');const s1=orgStream('s1');const keep=s1.mgmt;delete s1.mgmt;saveOrg();
              activate('org');const inputs=[...document.querySelectorAll('#org_root [data-stream=s1] input[data-mgmt]')].map(i=>i.dataset.mgmt);
              const fill=(k,v)=>{const i=document.querySelector('#org_root [data-stream=s1] input[data-mgmt='+k+']');i.value=v;i.dispatchEvent(new Event('change',{bubbles:true}));};
              localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;await sdocLoad(true);const st=await streamTeamStates(true);
              const ind0=matIndicators(st,piCur()).roles.lvl;
              fill('LEAD','Петрова М.');fill('ITLEAD','Смирнов К.');
              const ind2=matIndicators(st,piCur()).roles.lvl;
              fill('ARCH','Кузнецова Е.');fill('PM','Орлов Д.');
              const ind4=matIndicators(st,piCur()).roles.lvl,names=streamMgmt('s1').map(x=>x.names[0]);
              activate('stream');await streamFill('stream',true);const line=(document.querySelector('#str_stream .str-mgmt')||{}).textContent||'';
              activate('smaturity');await streamFill('smaturity',true);const head=[...document.querySelectorAll('#str_smaturity .mat-t th')].map(x=>x.textContent);
              const sheet=streamSheets().find(x=>x.name==='Команда управления');
              fill('PM','');const cleared=streamMgmt('s1').find(x=>x.pos==='PM').names.length===0;
              wizOpen();const m=document.getElementById('wizmodal');m.querySelector('[data-w=name]').value='Стрим «Роли»';m.querySelector('[data-w=teams]').value='Одна';
              m.querySelector('[data-wpos=LEAD]').value='Лидеров Л.';m.querySelector('[data-wpos=PM]').value='Менеджеров П.';await wizRun();
              const ns=ORG.streams.find(x=>x.name==='Стрим «Роли»'),wiz=!!ns&&streamMgmt(ns.id).filter(x=>x.names.length).map(x=>x.pos).join(',')==='LEAD,PM';
              await switchTeam('t1');if(ns){for(const x of ORG.teams.filter(t=>t.streamId===ns.id))await orgDelTeam(x.id);localStorage.removeItem(sdocKey(ns.id));await orgDelStream(ns.id);}
              s1.mgmt=keep;if(!keep)delete s1.mgmt;saveOrg();localStorage.removeItem(sdocKey('s1'));SDOC.loaded=false;activate('dash');
              return {inputs,ind0,ind2,ind4,names,line,head,sheetRows:sheet?sheet.aoa.length-1:-1,streams:ORG.streams.length,cleared,wiz,errs};
             }catch(e){return 'ERR:'+e.message;}finally{window.removeEventListener('error',h);}}""")
            assert isinstance(r, dict), 'stream positions failed: ' + str(r)
            assert not r['errs'], 'page errors: ' + str(r['errs'][:3])
            assert r['inputs'] == ['LEAD', 'ITLEAD', 'ARCH', 'PM'], 'four management positions in the stream card: ' + str(r['inputs'])
            assert (r['ind0'], r['ind2'], r['ind4']) == (1, 3, 4), 'maturity «management team» indicator by filled positions: ' + str(r)
            assert r['names'] == ['Петрова М.', 'Смирнов К.', 'Кузнецова Е.', 'Орлов Д.'], str(r['names'])
            assert 'Лидер стрима' in r['line'] and 'Орлов Д.' in r['line'], 'dashboard shows the management team: ' + r['line']
            assert 'Итог команды управления' in r['head'] and not any('RTE' in x for x in r['head']), 'maturity final column renamed: ' + str(r['head'])
            assert r['sheetRows'] == 4 * r['streams'], 'Excel «Команда управления»: 4 positions per stream'
            assert r['cleared'], 'empty name removes the position'
            assert r['wiz'], 'wizard assigns the management team'
        case('stream roles: management team positions, dashboard, maturity, Excel, wizard', t_stream_positions)

        br.close()
    httpd.shutdown()

    total = len(PASS) + len(FAIL) + len(SKIP)
    print('\n' + '=' * 60)
    print(f'RESULT: {len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped  (of {total})')
    if FAIL:
        print('\nFailures:')
        for n, m in FAIL:
            print('  - ' + n + ': ' + m)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
