"""Team context for analytics: the same access rule as the Java API (OrgService.effectiveRole).

  - global ADMIN -> every team;
  - a user without memberships -> their global role on every team;
  - otherwise -> the higher of the TEAM membership and the membership on the team's STREAM; none -> no access.
Each team's data lives in its own schema (org_teams.schema_name; NULL = default schema).
"""
import re

RANK = ["VIEWER", "EDITOR", "ADMIN"]
DEFAULT_TEAM = "t1"
_SAFE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


def effective_role(global_role, memberships, team):
    """memberships: [{"scope_type", "scope_id", "role"}]; team: {"id", "stream_id"} -> role or None."""
    if global_role == "ADMIN":
        return "ADMIN"
    if not memberships:
        return global_role
    best = None
    for m in memberships:
        hit = (m["scope_type"] == "TEAM" and m["scope_id"] == team["id"]) or \
              (m["scope_type"] == "STREAM" and m["scope_id"] == team["stream_id"])
        if hit and (best is None or RANK.index(m["role"]) > RANK.index(best)):
            best = m["role"]
    return best


def safe_schema(name):
    """Schema names come from org_teams (server-generated), but never interpolate an unchecked identifier."""
    if name is None:
        return None
    if not _SAFE.match(name):
        raise ValueError("bad schema name")
    return name
