"""FastAPI analytics service. Computes sprint metrics from PostgreSQL (read-only).

Data endpoints require the SAME bearer session token as the Java API (validated against the
shared app_sessions table), so analytics does not silently bypass application authentication.
Set ANALYTICS_AUTH_ENABLED=false only for local dev/tests. /analytics/health stays public.
Metrics are computed for ONE team: the X-Team-Id header (default — the first team), with the same
per-team / per-stream access rule as the Java API (app/org.py).
"""
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import db
from . import compute as C

AUTH_ENABLED = os.getenv("ANALYTICS_AUTH_ENABLED", "true").lower() in ("1", "true", "yes", "on")
CORS_ORIGINS = [o.strip() for o in os.getenv("ANALYTICS_CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]

app = FastAPI(title="Управление стримами и командами — сервис аналитики", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET"], allow_headers=["*"],
)


def require_auth(authorization: str = Header(default=None), x_auth_token: str = Header(default=None)):
    """Validate a bearer session token against the shared app_sessions table -> (username, role)."""
    if not AUTH_ENABLED:
        return None
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_auth_token:
        token = x_auth_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        with db.engine.connect() as c:
            row = c.execute(text("SELECT expires_at, username, role FROM app_sessions WHERE token = :t"),
                            {"t": token}).fetchone()
    except Exception:
        raise HTTPException(status_code=503, detail="auth_unavailable")
    if row is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    exp = row[0]
    if exp is not None:
        if getattr(exp, "tzinfo", None) is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="session_expired")
    return (row[1], row[2])


def team_schema(x_team_id: str = Header(default=None), user=Depends(require_auth)):
    """Schema of the requested team after the access check (None = default schema)."""
    username, role = user if user else (None, None)
    try:
        schema, _ = db.team_context(x_team_id, username, role)
    except LookupError:
        raise HTTPException(status_code=404, detail="team_not_found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden")
    return schema


@app.get("/analytics/health")
def health():
    try:
        db.ping()
        return {"status": "ok", "service": "python-analytics", "db": "up"}
    except Exception as e:  # noqa: BLE001
        return {"status": "degraded", "service": "python-analytics", "db": "down", "error": str(e)}


@app.get("/analytics/metrics")
def metrics(schema=Depends(team_schema)):
    return C.compute(db.load_state(schema))


@app.get("/analytics/rice")
def rice(schema=Depends(team_schema)):
    return {"items": C.rice_ranked(db.load_state(schema))}


@app.get("/analytics/burndown")
def burndown(schema=Depends(team_schema)):
    return C.burndown(db.load_state(schema))


@app.get("/analytics/dependencies")
def dependencies(schema=Depends(team_schema)):
    return C.deps_summary(db.load_state(schema))
