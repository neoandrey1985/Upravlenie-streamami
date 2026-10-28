-- Platform (cross-team) schema of «Управление стримами и командами».
-- Lives ONLY in the default schema (public) and has its own history table (platform_schema_history),
-- so its versions never collide with the team migrations in db/migration inherited from the base project.
-- Each team's data lives in its own schema (team_<id>) migrated with db/migration; the first team uses public.

CREATE TABLE IF NOT EXISTS org_streams (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  descr      TEXT,
  ord        INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS org_teams (
  id          TEXT PRIMARY KEY,
  stream_id   TEXT NOT NULL REFERENCES org_streams(id),
  name        TEXT NOT NULL,
  schema_name TEXT,                 -- NULL = default schema (the first team)
  ord         INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMP
);

-- Per-stream / per-team roles. A user without any membership keeps the global role on every team.
CREATE TABLE IF NOT EXISTS org_memberships (
  pk         BIGSERIAL PRIMARY KEY,
  username   TEXT NOT NULL,
  scope_type TEXT NOT NULL,         -- STREAM | TEAM
  scope_id   TEXT NOT NULL,
  role       TEXT NOT NULL,         -- VIEWER | EDITOR
  UNIQUE (username, scope_type, scope_id)
);
