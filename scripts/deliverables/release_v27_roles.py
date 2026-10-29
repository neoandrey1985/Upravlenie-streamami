# -*- coding: utf-8 -*-
"""v2.7.0: ролевая модель стрима в документах — команда управления стрима (лидер стрима, ИТ-лидер стрима, архитектор,
проектный менеджер): пункты в руководстве пользователя (20.3), описаниях («Стримы и команды») и руководстве
администратора (гл. 13); RTE заменяется командой управления во всех текстах; версия. Идемпотентно.
Запуск: python scripts/deliverables/release_v27_roles.py"""
import glob, os, pathlib, re, docx

os.chdir(pathlib.Path(__file__).resolve().parents[2])
P = "Управление_стримами_и_командами"
OLDV, NEWV = "2.6.0", "2.7.0"
MARK = "Команда управления стрима:"
UG = [MARK + " лидер стрима, ИТ-лидер стрима, архитектор и проектный менеджер. Состав виден в карточке стрима («Стримы и команды»), "
      "на дашборде и в зрелости стрима; мастер «Новый стрим» назначает его сразу.",
      "Права должностей (с сервером): лидер и ИТ-лидер стрима — редакторы данных стрима и всех его команд; архитектор и проектный менеджер — "
      "редакторы данных стрима (фичи, PI, зависимости, ROAM, Scrum of Scrums, System Demo, зрелость), данные команд — только просмотр.",
      "С сервером должность назначает администратор в «Ролях в стримах и командах»: пользователь, стрим и должность (права выставляются автоматически). "
      "Без сервера в карточке стрима указываются ФИО."]
DESC = (MARK + " лидер стрима и ИТ-лидер стрима (правят стрим и все его команды), архитектор и проектный менеджер (правят данные стрима, "
        "команды — просмотр). Итоговый уровень зрелости стрима фиксирует команда управления.")
ADM = [MARK + " должности назначаются на стрим (org_memberships.position, платформенная миграция V3): LEAD — лидер стрима, ITLEAD — ИТ-лидер стрима, "
       "ARCH — архитектор, PM — проектный менеджер. POST /api/org/memberships с полем position (только scopeType = STREAM); роль доступа при этом — EDITOR.",
       "Права должностей: LEAD и ITLEAD — редакторы данных стрима и всех его команд; ARCH и PM — редакторы документа стрима, на командах стрима — VIEWER. "
       "Правило едино для Java API, аналитики (Python) и доски; GET /api/org возвращает состав команды управления каждого стрима (streams[].mgmt)."]
RTE = [("Итог RTE", "Итог команды управления"), ("итог RTE", "итог команды управления"), ("RTE фиксирует", "команда управления стрима фиксирует"),
       ("(RTE или медиана", "(команда управления или медиана"), ("RTE и Product Management работают регулярно", "лидер стрима и ИТ-лидер работают регулярно"),
       ("руководитель стрима (RTE)", "команда управления стрима"), ("RTE", "команда управления стрима")]


def pars(d):
    yield from d.paragraphs
    for t in d.tables:
        for r in t.rows:
            for c in r.cells: yield from c.paragraphs
    for s in d.sections:
        for hf in (s.header, s.footer): yield from hf.paragraphs


def replace_all(d):
    n = 0
    for p in pars(d):
        txt = p.text
        if "RTE" not in txt and OLDV not in txt: continue
        new = txt
        for a, b in RTE: new = new.replace(a, b)
        new = new.replace(OLDV, NEWV)
        if new != txt:
            for r in p.runs: r.text = ""
            if p.runs: p.runs[0].text = new
            n += 1
    return n


def after(ref, text, style):
    np_ = ref.insert_paragraph_before(text, style=style); ref._p.addnext(np_._p); return np_


fn = f"Руководство_пользователя_{P}.docx"; d = docx.Document(fn)
if not any(p.text.startswith(MARK) for p in d.paragraphs):
    ps = d.paragraphs; i = next(k for k, p in enumerate(ps) if p.style.name.startswith("Heading") and p.text.startswith("20.3 "))
    j = next(k for k in range(i + 1, len(ps)) if ps[k].style.name.startswith("Heading"))
    for line in UG: ps[j].insert_paragraph_before(line, style="List Bullet")
    st = "добавлено"
else: st = "уже есть"
n = replace_all(d); d.save(fn); print(fn[:58], "20.3:", st, "замен:", n)
for fn in (f"Иллюстрированное_описание_{P}.docx", f"Описание_{P}.docx"):
    d = docx.Document(fn)
    if not any(p.text.startswith(MARK) for p in d.paragraphs):
        ps = d.paragraphs; i = next(k for k, p in enumerate(ps) if p.style.name == "Heading 2" and p.text.strip() == "Стримы и команды")
        ref = next(p for p in ps[i + 1:] if p.style.name == "List Bullet")
        ref.insert_paragraph_before(DESC, style="List Bullet"); st = "добавлено"
    else: st = "уже есть"
    n = replace_all(d); d.save(fn); print(fn[:58], "раздел:", st, "замен:", n)
fn = f"Руководство_администратора_{P}.docx"; d = docx.Document(fn)
if not any(p.text.startswith(MARK) for p in d.paragraphs):
    ref = next(p for p in d.paragraphs if p.text.startswith("Эффективная роль на команде"))
    last = ref
    for line in ADM: last = after(last, line, ref.style)
    st = "добавлено"
else: st = "уже есть"
n = replace_all(d); d.save(fn); print(fn[:58], "гл. 13:", st, "замен:", n)
for fn in sorted(glob.glob(f"*_{P}.docx")):
    if "пользователя" in fn or "описание" in fn.lower() or "администратора" in fn: continue
    d = docx.Document(fn); n = replace_all(d); d.save(fn); print(fn[:58], "замен:", n)
left = {fn: sum(p.text.count("RTE") for p in pars(docx.Document(fn))) for fn in glob.glob(f"*_{P}.docx")}
print("RTE осталось:", {k[:30]: v for k, v in left.items() if v})
