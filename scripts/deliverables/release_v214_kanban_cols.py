# -*- coding: utf-8 -*-
"""v2.14.0: перетаскивание колонок на Kanban-доске — в руководствах, описаниях и презентации;
версия во всех .docx. Снимок — capture_shots.py --only kanban (kanban.jpg). Миграций нет.
Идемпотентно. Запуск: python scripts/deliverables/release_v214_kanban_cols.py"""
import copy, glob, os, pathlib, re, docx
from docx.shared import Inches
from docx.text.paragraph import Paragraph
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

os.chdir(pathlib.Path(__file__).resolve().parents[2])
SH = pathlib.Path("build/shots")
P = "Управление_стримами_и_командами"
OLDV, NEWV = "2.13.1", "2.14.0"
OLDDATE, NEWDATE = "29.10.2026", "27.11.2026"
# точечные замены / дополнения в уже существующих абзацах
REPL = [
    ("«＋ Колонка» — добавить новый статус-колонку в текущую доску; «✕» в заголовке колонки удаляет пустую колонку.",
     "«＋ Колонка» — добавить новый статус-колонку в текущую доску; порядок колонок меняется перетаскиванием заголовка (ручка ⠿); «✕» в заголовке удаляет пустую колонку."),
    ("«＋ Колонка» (администратор) — добавляет новый статус-колонку на доску. Как работает: запрашивает название статуса; задачи можно будет перетащить в новую колонку.",
     "«＋ Колонка» (администратор) — добавляет новый статус-колонку на доску. Как работает: запрашивает название статуса; задачи можно будет перетащить в новую колонку. Порядок колонок меняется перетаскиванием заголовка (ручка ⠿) — в том числе сразу после добавления; порядок сохраняется в настройках доски."),
]
H = "Kanban: порядок колонок"
UG_EXTRA = ("5.3 Kanban-доски: порядок колонок",
            "Администратор меняет порядок колонок на доске перетаскиванием заголовка — удобно после «＋ Колонка» и для любой уже настроенной доски.",
            ["Перетащите заголовок колонки (ручка ⠿ слева) влево или вправо: подсветка показывает, вставить «до» или «после» соседней колонки.",
             "Переупорядочиваются только настроенные колонки доски (board.cols); «Состав релизов» по-прежнему строится из списка релизов.",
             "Карточки по-прежнему перетаскиваются отдельно — DnD колонок и карточек не конфликтуют. Порядок сохраняется вместе с данными команды.",
             "Доступно роли администратора; в режиме просмотра и редактора заголовки колонок не перетаскиваются."],
            [("kanban.jpg", "Kanban-доска: колонки со статусами и панель администратора")])
DESC = (H, "На Kanban-доске администратор меняет порядок колонок перетаскиванием заголовка (в том числе сразу после «＋ Колонка»); "
           "порядок сохраняется в настройках доски. Карточки по-прежнему переносятся между колонками отдельно.")
SLIDE_TITLE = "Kanban-доски по направлениям"
SLIDE_BODY = [
    "•  Доски по ролям, релизная и «Состав релизов».",
    "•  Карточки — между колонками; статус синхронен.",
    "•  Админ: «＋ Колонка» и порядок — перетаскиванием заголовка.",
    "•  WIP-лимиты по колонкам, фильтр по спринту.",
]
ADMIN_NOTE = ("Kanban-доски: администратор добавляет колонки-статусы («＋ Колонка»), меняет их порядок перетаскиванием заголовка "
              "и удаляет пустые колонки («✕»). Порядок колонок хранится в настройках доски (поле cols) вместе с данными команды.")


def put_before(anchor, p):
    anchor._p.addprevious(p._p); return p


def add_pic(d, anchor, img, cap, width):
    if not (SH / img).exists():
        print("   ! нет снимка", img); return
    p = d.add_paragraph(); p.alignment = 1; p.add_run().add_picture(str(SH / img), width=Inches(width)); put_before(anchor, p)
    c = d.add_paragraph(cap); c.alignment = 1
    for r in c.runs: r.italic = True
    put_before(anchor, c)


def set_par(p, text):
    for r in p.runs[1:]: r.text = ""
    if p.runs: p.runs[0].text = text
    else: p.add_run(text)


def replace_in(d, a, b):
    n = 0
    for p in d.paragraphs:
        if a in p.text and b not in p.text:
            set_par(p, p.text.replace(a, b)); n += 1
    return n


def version(d):
    pars = list(d.paragraphs) + [p for t in d.tables for r in t.rows for c in r.cells for p in c.paragraphs] \
        + [p for s in d.sections for hf in (s.header, s.footer) for p in hf.paragraphs]
    n = 0
    for p in pars:
        raw = p.text
        if OLDV not in raw and OLDDATE not in raw:
            continue
        touched = False
        for r in p.runs:
            if OLDV in r.text or OLDDATE in r.text:
                r.text = r.text.replace(OLDV, NEWV).replace(OLDDATE, NEWDATE); touched = True
        if OLDV in p.text or OLDDATE in p.text:
            set_par(p, p.text.replace(OLDV, NEWV).replace(OLDDATE, NEWDATE)); touched = True
        if touched: n += 1
    return n


def next_heading(d, i):
    return next(p for p in d.paragraphs[i + 1:] if p.style.name.startswith("Heading"))


def heading(d, text, lvl="Heading 2"):
    return next(k for k, p in enumerate(d.paragraphs) if p.style.name == lvl and p.text.strip() == text)


# --- руководство пользователя ---
fn = f"Руководство_пользователя_{P}.docx"; d = docx.Document(fn)
for a, b in REPL:
    n = replace_in(d, a, b); print("UG replace:", n, a[:40])
title, lead, bullets, pics = UG_EXTRA
if not any(p.text.strip() == title for p in d.paragraphs):
    anchor = next_heading(d, heading(d, "5.3 Kanban-доски"))
    # вставить подраздел сразу после блока 5.3 — перед следующим Heading 2
    put_before(anchor, d.add_paragraph(title, style="Heading 2"))
    put_before(anchor, d.add_paragraph(lead))
    for b in bullets:
        put_before(anchor, d.add_paragraph(b, style="List Bullet"))
    for img, cap in pics:
        add_pic(d, anchor, img, cap, 6.3)
    st = "добавлен"
else:
    st = "уже есть"
d.save(fn); print(fn[:58], "раздел:", st)

# --- описания ---
for fn, pics in ((f"Иллюстрированное_описание_{P}.docx", True), (f"Описание_{P}.docx", False)):
    d = docx.Document(fn)
    if not any(p.style.name.startswith("Heading") and p.text.strip() == H for p in d.paragraphs):
        anchor = next_heading(d, heading(d, "Kanban-доска"))
        put_before(anchor, d.add_paragraph(H, style="Heading 2"))
        put_before(anchor, d.add_paragraph(DESC[1]))
        if pics:
            add_pic(d, anchor, "kanban.jpg", H, 6.61)
        st = "добавлен"
    else:
        st = "уже есть"
    d.save(fn); print(fn[:58], "раздел:", st)

# --- руководство администратора: краткая заметка + версия ---
fn = f"Руководство_администратора_{P}.docx"
d = docx.Document(fn)
if ADMIN_NOTE not in "\n".join(p.text for p in d.paragraphs):
    # добавить в конец основного текста перед последним heading/пустым хвостом — ищем «Kanban» или пишем после первого абзаца с «доск»
    inserted = False
    for i, p in enumerate(d.paragraphs):
        if "Kanban" in p.text or "канбан" in p.text.lower():
            np = copy.deepcopy(p._p); p._p.addnext(np)
            q = Paragraph(np, p._parent); set_par(q, ADMIN_NOTE)
            inserted = True; break
    if not inserted:
        d.add_paragraph(ADMIN_NOTE)
    print(fn[:58], "заметка: добавлена")
else:
    print(fn[:58], "заметка: уже есть")
d.save(fn)

# --- версии во всех docx продукта ---
for fn in sorted(glob.glob(f"*_{P}.docx")) + sorted(glob.glob(f"Тестовая документация/*_{P}.docx")):
    if not pathlib.Path(fn).exists():
        continue
    d = docx.Document(fn); n = version(d); d.save(fn); print(f"{fn[:58]:58s} версия: {n}")


def texts(s):
    return [sh for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()]


def title_of(s):
    t = texts(s)
    return t[1].text_frame.text.strip() if len(t) > 1 else (t[0].text_frame.text.strip() if t else "")


def set_text(shape, text):
    tb = shape.text_frame._txBody; ps = tb.findall(qn('a:p'))
    for p in ps[1:]: tb.remove(p)
    runs = ps[0].findall(qn('a:r'))
    for r in runs[1:]: ps[0].remove(r)
    runs[0].find(qn('a:t')).text = text


def set_paras(shape, lines):
    tb = shape.text_frame._txBody; ps = tb.findall(qn('a:p')); tpl = copy.deepcopy(ps[0])
    for p in ps: tb.remove(p)
    for ln in lines:
        p = copy.deepcopy(tpl); runs = p.findall(qn('a:r'))
        for r in runs[1:]: p.remove(r)
        runs[0].find(qn('a:t')).text = ln; tb.append(p)


def parts(s):
    t = texts(s)
    icon = next(sh for sh in s.shapes if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and sh.has_text_frame)
    body = next(sh for sh in t if sh.text_frame.text.strip().startswith("•"))
    rest = [sh for sh in t if sh._element is not icon._element and sh._element is not body._element]
    pic = next(sh for sh in s.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE)
    return icon, rest[0], rest[1], body, pic


DECK = "Презентация_приложения.pptx"
prs = Presentation(DECK)
s = next((x for x in prs.slides if title_of(x) == SLIDE_TITLE), None)
if s is None:
    print("! слайд не найден:", SLIDE_TITLE)
else:
    icon, tsh, ssh, bsh, psh = parts(s)
    set_paras(bsh, SLIDE_BODY)
    if (SH / "kanban.jpg").exists():
        s.part.related_part(psh._element.find('.//' + qn('a:blip')).get(qn('r:embed')))._blob = (SH / "kanban.jpg").read_bytes()
    print(DECK, "обновлён слайд:", SLIDE_TITLE)
prs.save(DECK); print(DECK, "слайдов:", len(prs.slides))
