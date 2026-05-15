-- uuid-ossp extension removed: Azure Database for PostgreSQL Flexible Server
-- does not allow-list it by default, and the app generates UUIDs in Python.

CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY,
  topic TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT 'finance_economics',
  research_type TEXT CHECK(research_type IN ('exploratory','confirmatory','unknown')),
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID,
  coauthor_id UUID,
  parent_run_id UUID REFERENCES sessions(id),
  credits_spent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blueprints (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  content JSONB NOT NULL,
  status TEXT CHECK(status IN ('draft','locked')),
  locked_at TIMESTAMPTZ,
  blueprint_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS phases (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  agent_name TEXT NOT NULL,
  status TEXT CHECK(status IN (
    'pending','running','complete','failed_resumable',
    'failed_terminal','repair_required','needs_clarification',
    'evidence_blocked','paper_locked'
  )),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  summary_text TEXT,
  failure_reason TEXT,
  failure_mode TEXT,
  artifact_paths JSONB
);

CREATE TABLE IF NOT EXISTS papers (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  title TEXT,
  authors TEXT,
  year INTEGER,
  venue TEXT,
  abstract TEXT,
  doi TEXT,
  relevance_score FLOAT,
  cluster TEXT CHECK(cluster IN ('established','contested','adjacent')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pap_locks (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  blueprint_hash TEXT NOT NULL,
  locked_at TIMESTAMPTZ NOT NULL,
  hypothesis TEXT NOT NULL,
  primary_test TEXT NOT NULL,
  significance_threshold FLOAT NOT NULL,
  effect_size_minimum FLOAT
);

CREATE TABLE IF NOT EXISTS deviation_register (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  field_changed TEXT NOT NULL,
  changed_from TEXT,
  changed_to TEXT,
  reason TEXT NOT NULL,
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  agent_triggered_by TEXT,
  requires_researcher_approval BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS reviewer_scores (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  cycle INTEGER NOT NULL,
  identification_validity FLOAT,
  data_integrity FLOAT,
  statistical_rigor FLOAT,
  economic_significance FLOAT,
  benchmark_fairness FLOAT,
  robustness_burden FLOAT,
  overclaiming_risk FLOAT,
  average_score FLOAT,
  gate_passed BOOLEAN,
  findings JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repair_log (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  trigger_agent TEXT,
  trigger_finding TEXT,
  scope TEXT,
  pass_criterion TEXT,
  cycle_number INTEGER,
  approval_required BOOLEAN,
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  outcome TEXT,
  deviation_registered BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_events (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  event_type TEXT NOT NULL,
  agent TEXT,
  status TEXT,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coauthor_invitations (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  invited_email TEXT,
  invited_by UUID,
  status TEXT CHECK(status IN ('pending','accepted','declined','revoked')),
  created_at TIMESTAMPTZ,
  accepted_at TIMESTAMPTZ
);
