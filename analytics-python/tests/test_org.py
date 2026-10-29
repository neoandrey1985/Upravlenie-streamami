#!/usr/bin/env python3
"""Unit test of the analytics team-access rule (app/org.py) — no database needed.
Must match the Java OrgService.effectiveRole rule.
Run: python analytics-python/tests/test_org.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analytics-python"))

from app import org  # noqa: E402


def main():
    t2 = {"id": "t2", "stream_id": "s2"}
    t1 = {"id": "t1", "stream_id": "s1"}
    team_m = [{"scope_type": "TEAM", "scope_id": "t2", "role": "EDITOR"}]
    stream_m = [{"scope_type": "STREAM", "scope_id": "s2", "role": "VIEWER"}]

    assert org.effective_role("ADMIN", team_m, t1) == "ADMIN"                 # admin sees everything
    assert org.effective_role("EDITOR", [], t1) == "EDITOR"                   # no memberships -> global role
    assert org.effective_role("VIEWER", team_m, t2) == "EDITOR"               # team membership wins
    assert org.effective_role("VIEWER", team_m, t1) is None                   # other team -> no access
    assert org.effective_role("EDITOR", stream_m, t2) == "VIEWER"             # stream membership covers its teams
    assert org.effective_role("EDITOR", team_m + stream_m, t2) == "EDITOR"    # the higher role wins
    lead = [{"scope_type": "STREAM", "scope_id": "s2", "role": "EDITOR", "position": "LEAD"}]
    arch = [{"scope_type": "STREAM", "scope_id": "s2", "role": "EDITOR", "position": "ARCH"}]
    assert org.effective_role("VIEWER", lead, t2) == "EDITOR"                 # stream lead edits the stream's teams
    assert org.effective_role("VIEWER", arch, t2) == "VIEWER"                 # architect / PM: teams read-only
    assert org.effective_role("VIEWER", arch, t1) is None                     # other stream -> no access

    assert org.safe_schema(None) is None and org.safe_schema("team_t2") == "team_t2"
    for bad in ('x"; DROP SCHEMA public', "1abc", "a-b", ""):
        try:
            org.safe_schema(bad)
            raise AssertionError("accepted " + bad)
        except ValueError:
            pass
    print("analytics org access test OK")


if __name__ == "__main__":
    main()
