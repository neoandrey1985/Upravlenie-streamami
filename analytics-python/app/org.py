"""Team context for analytics: the same access rule as the Java API (OrgService.effectiveRole).

  - global ADMIN -> every team;
  - a user without memberships -> their global role on every team;
  - otherwise -> the higher of the TEAM membership and the membership on the team's STREAM; none -> no access.
    A STREAM membership with a management position ARCH (architect) or PM (project manager) gives VIEWER on the
    stream's teams; LEAD / ITLEAD (stream lead, IT lead) or no position — the membership role.
Each team's data lives in its own schema (org_teams.schema_name; NULL = default schema).
"""
import re

RANK = ["VIEWER", "EDITOR", "ADMIN"]
TEAM_EDIT_POSITIONS = {"LEAD", "ITLEAD"}
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
        role = None
        if m["scope_type"] == "TEAM" and m["scope_id"] == team["id"]:
            role = m["role"]
        elif m["scope_type"] == "STREAM" and m["scope_id"] == team["stream_id"]:
            pos = m.get("position")
            role = m["role"] if not pos or pos in TEAM_EDIT_POSITIONS else "VIEWER"
        if role and (best is None or RANK.index(role) > RANK.index(best)):
            best = role
    return best


def safe_schema(name):
    """Schema names come from org_teams (server-generated), but never interpolate an unchecked identifier."""
    if name is None:
        return None
    if not _SAFE.match(name):
        raise ValueError("bad schema name")
    return name
