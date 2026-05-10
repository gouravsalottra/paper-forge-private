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

CREATE TABLE IF NOT EXISTS hypothesis_lock (
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
    prompt_sha256 TEXT,
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

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    checkpoint_key TEXT NOT NULL,
    value_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, phase_name, checkpoint_key),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS token_budget (
    budget_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL,
    model TEXT,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS token_limits (
    run_id TEXT PRIMARY KEY,
    soft_limit_usd REAL NOT NULL DEFAULT 10.0,
    hard_limit_usd REAL NOT NULL DEFAULT 25.0,
    total_spent_usd REAL NOT NULL DEFAULT 0.0,
    last_updated TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE TABLE IF NOT EXISTS results_gate (
    run_id TEXT PRIMARY KEY,
    p_value_passes BOOLEAN DEFAULT FALSE,
    seed_consistent BOOLEAN DEFAULT FALSE,
    codeaudit_clean BOOLEAN DEFAULT FALSE,
    results_valid BOOLEAN GENERATED ALWAYS AS
        (p_value_passes AND seed_consistent AND codeaudit_clean) VIRTUAL,
    last_updated TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);
