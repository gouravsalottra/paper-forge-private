PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    completed_at TEXT,
    paper_md_path TEXT,
    seed_query TEXT,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER,
    run_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    completed_at TEXT,
    details_json TEXT,
    UNIQUE(run_id, phase_name)
);

CREATE TABLE IF NOT EXISTS pap_lock (
    run_id TEXT PRIMARY KEY,
    locked_at TEXT,
    locked_by TEXT,
    pap_sha256 TEXT,
    forge_started_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    job TEXT,
    result_flag TEXT NOT NULL,
    phase_name TEXT,
    agent_name TEXT,
    pap_id TEXT,
    status TEXT,
    score REAL,
    output_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS server_health_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER,
    run_id TEXT,
    server_name TEXT NOT NULL,
    status TEXT NOT NULL,
    checked_at TEXT,
    detail TEXT,
    latency_ms REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pap_id TEXT,
    run_id TEXT NOT NULL,
    title TEXT,
    abstract TEXT,
    score REAL,
    status TEXT,
    content TEXT,
    updated_at TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
