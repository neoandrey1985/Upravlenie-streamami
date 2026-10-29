"""PostgreSQL access for the analytics service. Reads the same tables the Java API writes."""
import os
from sqlalchemy import create_engine, text

from . import org

DB_URL = os.getenv(
    "DB_URL_PY",
    "postgresql+psycopg2://streams:streams@localhost:5432/streams",
)
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)


def load_state(schema=None):
    """Assemble a dict shaped like the front-end ST object from the relational tables of one team.
    schema: the team's schema (None = default schema, i.e. the first team)."""
    with engine.connect() as c:
        if schema:
            c.execute(text('SET search_path TO "%s"' % org.safe_schema(schema)))
        try:
            return _assemble(lambda sql: [dict(r._mapping) for r in c.execute(text(sql))])
        finally:
            if schema:
                c.execute(text("SET search_path TO DEFAULT"))   # pooled connection: never leak a team schema


def _assemble(_rows):
    pr = _rows("SELECT * FROM params WHERE id = 1")
    p = pr[0] if pr else {}
    st = {
        "params": {
            "name": p.get("name"), "start": p.get("start_date"), "sprintDays": p.get("sprint_days"),
            "focus": p.get("focus"), "today": p.get("today_date"), "goal": p.get("goal"),
            "sprints": p.get("sprints") or 11,
        },
        "budget": {"rate": p.get("budget_rate"), "total": p.get("budget_total")},
        "ttmTarget": p.get("ttm_target") or 15,
        "team": [{"name": r["name"], "role": r["role"], "avail": r["avail"], "absent": r["absent"]}
                 for r in _rows("SELECT * FROM team ORDER BY ord")],
        "tasks": [{"id": r["task_id"], "title": r["title"], "role": r["role"], "type": r["type"],
                   "est": r["est"], "status": r["status"], "sprint": r["sprint"], "dep": r["dep"],
                   "started": r["started"], "done": r["done"]}
                  for r in _rows("SELECT * FROM tasks ORDER BY ord")],
        "releases": [{"id": r["rel_id"], "name": r["name"], "sfrom": r["sfrom"], "sto": r["sto"], "status": r["status"]}
                     for r in _rows("SELECT * FROM releases ORDER BY ord")],
        "milestones": [{"id": r["ms_id"], "name": r["name"], "sprint": r["sprint"], "status": r["status"], "rel": r["rel"]}
                       for r in _rows("SELECT * FROM milestones ORDER BY ord")],
        "bugs": [{"id": r["bug_id"], "sprint": r["sprint"], "sev": r["sev"], "status": r["status"], "task": r["task"]}
                 for r in _rows("SELECT * FROM bugs ORDER BY ord")],
        "calendar": [{"date": r["cdate"], "name": r["name"]} for r in _rows("SELECT * FROM calendar ORDER BY ord")],
        "rice": [{"id": r["rice_id"], "task": r["task"], "name": r["name"], "reach": r["reach"], "impact": r["impact"],
                  "conf": r["conf"], "effort": r["effort"]} for r in _rows("SELECT * FROM rice ORDER BY ord")],
        "moscow": [{"id": r["ms_id"], "task": r["task"], "name": r["name"], "category": r["category"],
                    "note": r["note"]} for r in _rows("SELECT * FROM moscow ORDER BY ord")],
        "faq": [{"id": r["faq_id"], "category": r["category"], "q": r["question"],
                 "a": r["answer"]} for r in _rows("SELECT * FROM faq ORDER BY ord")],
        "grooming": [{"id": r["grm_id"], "task": r["task"], "date": r["gdate"], "item": r["item"], "action": r["action"],
                      "est": r["est"], "ready": r["ready"], "owner": r["owner"], "notes": r["notes"]}
                     for r in _rows("SELECT * FROM grooming ORDER BY ord")],
        "demo": [{"id": r["demo_id"], "sprint": r["sprint"], "date": r["ddate"], "item": r["item"],
                  "presenter": r["presenter"], "stakeholders": r["stakeholders"], "feedback": r["feedback"],
                  "status": r["status"]} for r in _rows("SELECT * FROM demo ORDER BY ord")],
        "daily": [{"id": r["daily_id"], "date": r["ddate"], "sprint": r["sprint"], "participant": r["participant"],
                   "yesterday": r["yesterday"], "today": r["today"], "blocker": r["blocker"]}
                  for r in _rows("SELECT * FROM daily ORDER BY ord")],
        "vacation": [{"id": r["vac_id"], "member": r["member"], "type": r["vtype"], "from": r["dfrom"],
                      "to": r["dto"], "days": r["days"], "status": r["status"], "notes": r["notes"]}
                     for r in _rows("SELECT * FROM vacation ORDER BY ord")],
        "birthdays": [{"id": r["bd_id"], "member": r["member"], "date": r["bdate"], "role": r["role"],
                       "notes": r["notes"]} for r in _rows("SELECT * FROM birthdays ORDER BY ord")],
        "deps": [{"id": r["dep_id"], "item": r["item"], "stream": r["stream"], "dir": r["dir"],
                  "status": r["status"], "task": r["task"]} for r in _rows("SELECT * FROM deps ORDER BY ord")],
        "dod": [{"crit": r["crit"], "done": r["done"]} for r in _rows("SELECT * FROM dod ORDER BY ord")],
    }
    return st


def team_context(team_id, username, global_role):
    """Resolve a team for a user: returns (schema, role) or raises LookupError/PermissionError."""
    with engine.connect() as c:
        try:
            row = c.execute(text("SELECT id, stream_id, schema_name FROM org_teams WHERE id = :i"),
                            {"i": team_id or org.DEFAULT_TEAM}).fetchone()
        except Exception:   # platform tables not created yet (old database): only the default team exists
            c.rollback()
            if team_id in (None, "", org.DEFAULT_TEAM):
                return None, global_role
            raise LookupError("team_not_found")
        if row is None:
            raise LookupError("team_not_found")
        mem = [] if username is None else [dict(r._mapping) for r in c.execute(
            text("SELECT * FROM org_memberships WHERE username = :u"), {"u": username})]
    role = "EDITOR" if username is None else org.effective_role(global_role, mem, {"id": row[0], "stream_id": row[1]})
    if role is None:
        raise PermissionError("forbidden")
    return row[2], role


def ping():
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return True
