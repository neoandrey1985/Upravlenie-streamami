# -*- coding: utf-8 -*-
"""Regenerate «Архитектура приложения.docx» — a standalone document with all architecture
diagrams and dependencies: overall architecture, microservices architecture, and database
architecture (ER-style domain map + full table catalog).

Reusable: the DB catalog and diagram are built by PARSING the Flyway migrations
(backend-java/.../db/migration/V*.sql), so new tables/migrations appear automatically.
The two hand-authored diagrams live in scripts/deliverables/arch_assets/*.svg.

Usage: python scripts/deliverables/build_architecture_doc.py
Deps: playwright (chromium), pillow, python-docx.
"""
import re, glob, html, pathlib, sys
from playwright.sync_api import sync_playwright
from PIL import Image
import docx
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = pathlib.Path(__file__).resolve().parents[2]
ASSETS = pathlib.Path(__file__).resolve().parent / "arch_assets"
MIGR_DIR = ROOT / "backend-java" / "src" / "main" / "resources" / "db" / "migration"
PLAT_DIR = MIGR_DIR.parent / "platform"   # платформа стримов и команд (своя история Flyway)
BUILD = ROOT / "build" / "arch"
BUILD.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "Архитектура_приложения.docx"
VER = re.search(r"const APP_VERSION='([^']+)'", (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")).group(1)

# domain + purpose per table (tables not listed fall back to «—»)
PURPOSE = {
 "params": ("Система", "Параметры проекта: старт, число спринтов, focus factor, цель, бюджет"),
 "app_meta": ("Система", "Версия состояния для оптимистичной блокировки /api/state"),
 "app_users": ("Система", "Пользователи и роли (серверная авторизация)"),
 "app_sessions": ("Система", "Сессии/токены авторизации"),
 "board_doc": ("Система", "Холст интерактивной доски (JSON-документ)"),
 "tasks": ("Планирование", "Бэклог: задачи/истории/эпики; оценка, статус, спринт, релиз, DoR, OKR, parent (WBS)"),
 "releases": ("Планирование", "Релизы по диапазону спринтов"),
 "milestones": ("Планирование", "Вехи, привязанные к спринтам/релизам"),
 "boards": ("Планирование", "Определения Kanban-досок (колонки, фильтр, WIP-лимиты)"),
 "okr": ("Планирование", "Цели квартала и Key Results"),
 "sprint_goals": ("Планирование", "Цель каждого спринта и её статус"),
 "rice": ("Планирование", "Приоритизация RICE"),
 "wsjf": ("Планирование", "Приоритизация WSJF (SAFe)"),
 "moscow": ("Планирование", "Приоритизация MoSCoW"),
 "story_map": ("Планирование", "Карта историй: активности × релизы"),
 "team": ("Команда", "Состав команды, роли, доступность, Scrum-мастер"),
 "skills": ("Команда", "Компетенции участников (Star Map)"),
 "raci": ("Команда", "Матрица ответственности RACI"),
 "stakeholders": ("Команда", "Реестр стейкхолдеров"),
 "vacation": ("Команда", "График отпусков/отсутствий"),
 "birthdays": ("Команда", "Дни рождения участников"),
 "tech_debt": ("Выпуск", "Реестр технического долга"),
 "deps": ("Выпуск", "Межстримовые зависимости"),
 "change_requests": ("Выпуск", "Запросы на изменение (CCB)"),
 "risks": ("Аналитика", "Реестр рисков"),
 "bugs": ("Аналитика", "Дефекты, серьёзность, DRE"),
 "issues": ("Аналитика", "Журнал проблем"),
 "experiments": ("Аналитика", "Эксперименты/гипотезы"),
 "radar": ("Аналитика", "Team Radar"),
 "daily": ("Церемонии", "Дэйли-стендапы"),
 "grooming": ("Церемонии", "Груминг бэклога"),
 "demo": ("Церемонии", "Демо спринта"),
 "retro": ("Церемонии", "Ретроспективы и action items"),
 "mood": ("Церемонии", "Настроение команды"),
 "kudos": ("Церемонии", "Благодарности"),
 "agile_maturity": ("Церемонии", "Уровень Agile-зрелости"),
 "impediments": ("Церемонии", "Журнал импедиментов"),
 "lessons": ("Церемонии", "Извлечённые уроки"),
 "poker": ("Церемонии", "Planning Poker"),
 "dod": ("Контроль", "Definition of Done"),
 "dor_items": ("Контроль", "Definition of Ready"),
 "scope_log": ("Контроль", "Журнал изменений состава (scope creep)"),
 "decisions": ("Контроль", "Журнал решений (ADR)"),
 "portfolio": ("Контроль", "Портфель проектов"),
 "faq": ("Контроль", "Частые вопросы"),
 "calendar": ("Контроль", "Календарь праздников"),
 "team_health": ("Церемонии", "Team Health Check (Spotify Squad): оценки измерений здоровья команды"),
 "deployments": ("Выпуск", "Деплои — для DORA (частота, lead time, change failure rate)"),
 "incidents": ("Аналитика", "Прод-инциденты и постмортемы — MTTR для DORA"),
 "ishikawa_cats": ("Аналитика", "Категории диаграммы Исикавы (причины срыва сроков)"),
 "ishikawa": ("Аналитика", "Причины диаграммы Исикавы с весом и привязкой к категории"),
 "org_streams": ("Платформа", "Стримы (потоки ценности): название, описание, порядок"),
 "org_teams": ("Платформа", "Команды стримов; schema_name — схема БД с данными команды (пусто у первой — public)"),
 "org_memberships": ("Платформа", "Роли пользователей в стримах и командах (VIEWER / EDITOR) и должности команды управления стрима (position)"),
 "org_stream_docs": ("Платформа", "Документ стрима (фичи, PI, цели, зависимости, ROAM, Scrum of Scrums, System Demo) с версией"),
}
DOMAIN_ORDER = ["Система", "Планирование", "Команда", "Выпуск", "Аналитика", "Церемонии", "Контроль", "Платформа"]
DOMAIN_STYLE = {"Система": ("#E4EBFB", "#2D5BE3"), "Планирование": ("#E4EBFB", "#2D5BE3"),
                "Команда": ("#EAF6F0", "#1F9D6B"), "Выпуск": ("#EAF6F0", "#1F9D6B"),
                "Аналитика": ("#FBF3E0", "#C98A00"), "Церемонии": ("#FBF3E0", "#C98A00"),
                "Контроль": ("#F2F5FA", "#5A6B82"), "Платформа": ("#F1ECFB", "#8A5BD6")}


def parse_migrations(d=MIGR_DIR):
    files = sorted(glob.glob(str(d / "V*.sql")),
                   key=lambda f: int(re.match(r"V(\d+)", pathlib.Path(f).name).group(1)))
    tables, order, migr = {}, [], []
    for f in files:
        name_v = re.match(r"(V\d+)", pathlib.Path(f).name).group(1)
        sql = open(f, encoding="utf-8").read()
        migr.append(name_v)
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);", sql, re.S | re.I):
            cols = []
            for line in m.group(2).split("\n"):
                line = line.strip().rstrip(",")
                mm = re.match(r"(\w+)\s+[A-Za-z]", line)
                if mm and mm.group(1).upper() not in ("PRIMARY", "CONSTRAINT", "UNIQUE", "FOREIGN"):
                    cols.append(mm.group(1))
            tables[m.group(1)] = cols
            if m.group(1) not in order:
                order.append(m.group(1))
        for m in re.finditer(r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)", sql, re.I):
            if m.group(1) in tables:
                tables[m.group(1)].append(m.group(2))
    return order, tables, migr


def db_svg(order):
    groups = {d: [] for d in DOMAIN_ORDER}
    for t in order:
        dom = PURPOSE.get(t, ("Контроль", ""))[0]
        groups.setdefault(dom, []).append(t)
    xs = [70, 590, 1110, 1630]; W = 490
    layout = [(190, DOMAIN_ORDER[:4]), (660, DOMAIN_ORDER[4:8])]
    s = ['<svg width="2160" height="1215" viewBox="0 0 2160 1215" xmlns="http://www.w3.org/2000/svg">',
         '<rect width="2160" height="1215" fill="#FFFFFF"/>',
         '<text x="80" y="76" font-size="46" font-weight="700" fill="#16202E" font-family="Segoe UI,Arial">Архитектура базы данных</text>',
         '<text x="80" y="118" font-size="25" fill="#5A6B82" font-family="Segoe UI,Arial">%d таблиц команды (своя схема у каждой команды) + %d табл. платформы в public. Состояние команды — GET/PUT /api/state (X-Team-Id).</text>' % (len([t for t in order if not t.startswith("org_")]), len([t for t in order if t.startswith("org_")]))]
    for y, doms in layout:
        for col, dom in enumerate(doms):
            x = xs[col]; bg, stroke = DOMAIN_STYLE[dom]; tbls = groups.get(dom, [])
            h = 70 + len(tbls) * 34 + 20
            s.append('<rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="%s" stroke="%s" stroke-width="2"/>' % (x, y, W, h, bg, stroke))
            s.append('<text x="%d" y="%d" font-size="25" font-weight="700" fill="#16202E" font-family="Segoe UI,Arial">%s</text>' % (x + 22, y + 42, html.escape(dom)))
            for i, t in enumerate(tbls):
                s.append('<text x="%d" y="%d" font-size="22" fill="#16202E" font-family="Consolas,monospace">• %s</text>' % (x + 26, y + 80 + i * 34, t))
    s.append('</svg>')
    return "".join(s)


def render(svg, out_jpg):
    htmlp = BUILD / (out_jpg.stem + ".html")
    htmlp.write_text('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0}'
                     'body{width:2160px;height:1215px;background:#fff}</style></head><body>' + svg + '</body></html>', encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 2160, "height": 1215}, device_scale_factor=1)
        pg = ctx.new_page(); pg.goto(htmlp.as_uri()); pg.wait_for_timeout(350)
        raw = BUILD / (out_jpg.stem + "_raw.png"); pg.screenshot(path=str(raw)); ctx.close(); b.close()
    im = Image.open(raw).convert("RGB")
    if im.size != (2160, 1215):
        im = im.resize((2160, 1215))
    im.save(out_jpg, quality=90); raw.unlink()


def img(doc, path, w=6.61):
    if path.exists():
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(path), width=Inches(w))


def tbl(doc, headers, rows):
    t = doc.add_table(rows=1, cols=len(headers)); t.style = "Light Grid Accent 1"
    for i, h in enumerate(headers):
        t.rows[0].cells[i].text = ""; r = t.rows[0].cells[i].paragraphs[0].add_run(h); r.bold = True
    for row in rows:
        c = t.add_row().cells
        for i, v in enumerate(row):
            c[i].text = str(v)


def main():
    order, tables, migr = parse_migrations()
    porder, ptables, pmigr = parse_migrations(PLAT_DIR)
    # платформенные миграции могут дополнять общие таблицы public (например, app_users.member_name — V4)
    for f in sorted(glob.glob(str(PLAT_DIR / "V*.sql"))):
        for m in re.finditer(r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS\s+(\w+)", open(f, encoding="utf-8").read(), re.I):
            if m.group(1) in tables and m.group(2) not in tables[m.group(1)]: tables[m.group(1)].append(m.group(2))
    order_all = order + porder; tables.update(ptables)
    render((ASSETS / "overall.svg").read_text(encoding="utf-8"), BUILD / "architecture.jpg")
    render((ASSETS / "microservices.svg").read_text(encoding="utf-8"), BUILD / "micro.jpg")
    render(db_svg(order_all), BUILD / "db.jpg")

    doc = docx.Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(1.0)
    doc.styles["Normal"].font.name = "Calibri"; doc.styles["Normal"].font.size = Pt(11)
    doc.add_heading("Архитектура приложения", level=0)
    doc.add_paragraph().add_run("Управление стримами и командами · v" + VER).italic = True
    doc.add_paragraph("Все диаграммы и зависимости архитектуры: общая архитектура, микросервисы и база данных. "
                      "Стек — полиглот (веб-SPA + Java + Python + PostgreSQL), разворачивается через docker-compose.")

    doc.add_heading("1. Общая архитектура", level=1)
    doc.add_paragraph("Единственная публичная точка входа — nginx (:8090): раздаёт SPA и проксирует к сервисам. "
                      "Бизнес-логика и данные — Java (Spring Boot), метрики — Python (FastAPI); общая PostgreSQL, в которой у каждой команды своя схема.")
    img(doc, BUILD / "architecture.jpg")
    doc.add_heading("Компоненты", level=2)
    tbl(doc, ["Компонент", "Технология", "Роль", "Доступ"], [
        ["Веб-интерфейс (SPA)", "Vanilla JS, один index.html", "UI, офлайн, экспорт", "через nginx :8090"],
        ["nginx (web)", "nginx", "reverse proxy, статика, /docs", ":8090 — публичный"],
        ["API (api)", "Java 17, Spring Boot", "REST /api/state, авторизация, Flyway, WS, интеграции", "внутренний"],
        ["Analytics", "Python, FastAPI", "движок метрик (/analytics)", "внутренний"],
        ["БД (db)", "PostgreSQL 16", "хранение + журнал/аудит", "внутренний, pgdata"]])

    doc.add_heading("2. Архитектура микросервисов", level=1)
    doc.add_paragraph("Четыре сервиса docker-compose в одной внутренней сети; наружу открыт только web (:8090).")
    img(doc, BUILD / "micro.jpg")
    doc.add_heading("Сервисы", level=2)
    tbl(doc, ["Сервис", "Образ / стек", "Зависит от", "Порт", "Назначение"], [
        ["web", "./frontend (nginx)", "api, analytics", "8090:80", "SPA, /docs, reverse-proxy"],
        ["api", "./backend-java (Spring Boot)", "db (healthy)", "внутр.", "REST, авторизация, Flyway, WS, интеграции"],
        ["analytics", "./analytics-python (FastAPI)", "db (healthy)", "внутр.", "метрики (read-only к БД)"],
        ["db", "postgres:16", "—", "внутр.", "PostgreSQL, pgdata, healthcheck"]])

    doc.add_heading("3. Архитектура базы данных", level=1)
    doc.add_paragraph("PostgreSQL хранит %d таблиц команды по доменам и %d таблицы платформы. Всё состояние — единый снимок GET/PUT /api/state с "
                      "оптимистичной блокировкой (app_meta). Связи логические (по строковым id). Схема — Flyway %s."
                      % (len(order), len(porder), "–".join([migr[0], migr[-1]])))
    img(doc, BUILD / "db.jpg")
    doc.add_heading("Миграции Flyway", level=2)
    MDESC = {"V1": "начальная схема и демо-данные", "V2": "пользователи и сессии", "V3": "поля задач и Kanban-доски",
             "V4": "холст доски", "V5": "компетенции (skills)", "V6": "Agile-зрелость", "V7": "Scrum-мастер",
             "V8": "цели спринтов и WSJF", "V9": "WIP, DoR, scope-лог, OKR-связь", "V10": "пакеты PM + иерархия работ (WBS)",
             "V11": "Team Health Check, деплои и инциденты (DORA)", "V12": "диаграмма Исикавы (категории и причины)"}
    tbl(doc, ["Версия", "Что добавляет"], [[v, MDESC.get(v, "")] for v in migr])
    doc.add_heading("Платформа стримов и команд", level=2)
    doc.add_paragraph("Платформенные таблицы живут только в схеме public и мигрируются отдельно (db/platform, история "
                      "platform_schema_history), поэтому их версии не пересекаются с миграциями команды, приходящими из базового проекта.")
    PDESC = {"V1": "стримы, команды, роли (org_streams, org_teams, org_memberships)", "V2": "документ стрима (org_stream_docs)", "V3": "должности команды управления стрима (org_memberships.position)"}
    tbl(doc, ["Версия платформы", "Что добавляет"], [[v, PDESC.get(v, "")] for v in pmigr])
    for line in ["Схема на команду: первая команда (t1) — public, каждая новая — team_<id>; набор таблиц команды одинаков и мигрируется теми же V1…V%s." % migr[-1][1:],
                 "Hibernate SCHEMA multi-tenancy: схема выбирается по команде запроса (TenantContext), код сущностей и StateService не меняется.",
                 "Доступ: эффективная роль на команде = роль ADMIN, или общая роль (если назначений нет), или максимум из ролей в команде и в её стриме.",
                 "Данные стрима — один JSON-документ на стрим с версией (409 при конфликте); сводки по стриму считаются по данным команд."]:
        doc.add_paragraph(line, style="List Bullet")
    doc.add_heading("Каталог таблиц", level=2)
    rows = []
    for name in order_all:
        dom, purp = PURPOSE.get(name, ("—", "—"))
        cols = tables.get(name, [])
        key = ", ".join(cols[:6]) + (" …" if len(cols) > 6 else "")
        rows.append([name, dom, str(len(cols)), key, purp])
    tbl(doc, ["Таблица", "Домен", "Колонок", "Ключевые поля", "Назначение"], rows)

    doc.add_heading("4. Зависимости и потоки данных", level=1)
    for line in ["Браузер → nginx (:8090) → SPA и проксирование API/Analytics.",
                 "SPA ↔ API: GET/PUT /api/state (полный снимок команды из заголовка X-Team-Id, блокировка версии).",
                 "SPA ↔ API: /api/org — стримы, команды, роли; /api/org/streams/{id}/doc — документ стрима.",
                 "SPA ↔ API: WebSocket /ws/board?team=<id> — доска в реальном времени, отдельная комната у каждой команды.",
                 "SPA → Analytics: /analytics — метрики выбранной команды (тот же токен и X-Team-Id).",
                 "API → PostgreSQL (CRUD + Flyway); Analytics → PostgreSQL (чтение).",
                 "API → внешние (исходящие): Atlassian (Jira, Confluence, Opsgenie, Bitbucket, Trello, JSM, Bamboo, Statuspage), Slack."]:
        doc.add_paragraph(line, style="List Bullet")
    doc.add_paragraph("Внешние интеграции опциональны (включаются переменными окружения); приложение работает и офлайн.")
    doc.add_paragraph().add_run("Сгенерировано для приложения «Управление стримами и командами» v" + VER + ".").italic = True
    doc.save(str(OUT))
    print("saved", OUT, OUT.stat().st_size, "bytes; tables:", len(order))


if __name__ == "__main__":
    main()
