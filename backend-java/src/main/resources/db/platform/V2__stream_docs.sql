-- Stream-level data (features, PI, PI objectives, ROAM risks, cross-team dependencies, Scrum of Scrums):
-- one JSON document per stream with an optimistic-concurrency version, like the team state.
CREATE TABLE IF NOT EXISTS org_stream_docs (
  stream_id  TEXT PRIMARY KEY REFERENCES org_streams(id),
  version    BIGINT NOT NULL DEFAULT 0,
  data       TEXT,
  updated_at TIMESTAMP,
  updated_by TEXT
);
