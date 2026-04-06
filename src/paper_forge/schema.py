"""SQLite DDL — single source of truth for table layout."""

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS aria_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  phase TEXT NOT NULL DEFAULT 'init',
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS routing_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  route TEXT NOT NULL,
  payload_json TEXT,
  correlation_id TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phase TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pap_row (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hypothesis_id TEXT NOT NULL UNIQUE,
  hypothesis_text TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pap_commit (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  committed_at TEXT NOT NULL,
  committed_content_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pap_lock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  sealed INTEGER NOT NULL DEFAULT 0 CHECK (sealed IN (0, 1)),
  sealed_at TEXT,
  seal_content_sha256 TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scout_literature (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT,
  uri TEXT,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS miner_dataset_manifest (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  manifest_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS miner_data_blob (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  logical_key TEXT NOT NULL,
  payload_json TEXT,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sigma_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  stats_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sigma_figure (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  path_ref TEXT,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forge_simulation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code_path TEXT,
  code_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forge_simulation_output (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sim_id INTEGER NOT NULL REFERENCES forge_simulation(id),
  output_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS codec_spec (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  spec_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS codec_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  audit_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS codec_fix_request (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quill_latex (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  latex_text TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hawk_review (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
