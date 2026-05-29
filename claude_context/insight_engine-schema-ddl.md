# Insight Engine — Database Schema (Azure SQL DDL)

> **Responsibility:** the physical Azure SQL schema for the Insight Engine's configuration and bronze-persistence tables. The engine mechanism and the logical bronze record contract live in `insight_engine.md`; the rule/strategy content lives in the runtime tables seeded from `Scoring Parameters.xlsx`.
> **Target:** `options-analyzer-db` · Entra ID auth · JSON stored as `NVARCHAR(MAX)`.
> **Decision Date:** 2026-05-22
>
> **Change Log**
> | Date | Change |
> |---|---|
> | 2026-05-28 | Added terminal_verdict column to engine_strategy_rule_junction (OTA-709). |
> | 2026-05-22 | Initial schema established. |

---

## 1. Conventions

These rules govern every table below.

- **Placement.** All tables live in `dbo`. Framework tables are name-prefixed: `engine_*` for configuration, `bronze_*` for persistence.
- **No domain literals as constraints.** Discriminator columns (`phase`, `candidate_type`, `verdict`, `record_type`) are free `varchar`. Their valid domains are registered as `SHARED` rows in `engine_lookups` and validated at engine load (`insight_engine.md` §6.6), never expressed as a `CHECK` enum. This keeps the framework tables domain-agnostic.
- **App-scoped identity.** `engine_rules`, `engine_strategies`, and `engine_lookups` each use a surrogate `INT IDENTITY` PK plus a natural key `(owner_app_id, <key>)`. The cross-app rule library lives under `owner_app_id = 'SHARED'`; OTA content under `'OTA'`. `SHARED` is a sentinel row in `engine_apps`, not a nullable column, because a SQL Server unique index permits only one `NULL`.
- **Junction parameter storage.** Mechanical fields (`evaluation_order`, `stop_if_fail`, `score_penalty`, `weight`, `enabled`, `rationale`) are typed columns. Variable per-rule parameters are a single `parameters NVARCHAR(MAX)` JSON column, validated at engine load against `engine_rules.parameter_schema`.
- **`payload_version` is namespaced by discriminator** — by `candidate_type` for snapshot records, by `phase` for decision records (`insight_engine.md` §4.3). `bronze_payload_contract` registers the shape of each `(record_type, discriminator_value, payload_version)` combination.
- **Bronze is append-only and carries no foreign keys.** All references out (`source_app_id`, `user_id`, `symbol`, `strategy_key`, `rule_key`, `subject_id`, `snapshot_id`) are denormalized soft keys, so the zone outlives the rows it describes and stays portable. Decision records correlate to their snapshot record by shared `snapshot_id` and `run_id`. Bronze stores string keys; the configuration tables' `INT` surrogates never appear in bronze.
- **Physical promotion follows the filter rule.** The bronze table promotes to typed columns every field used in a `WHERE`/`JOIN`/`GROUP BY` (`insight_engine.md` §4.3 golden rule), including `user_id` (data-isolation filter), `run_id`, and `subject_type`/`subject_id`. Everything else lives in `payload_json`. The logical record contract — two streams, `CandidateSnapshot` and `EvaluationDecision` — is unchanged.

---

## 2. Engine configuration tables

```sql
-- ============================================================================
--  ENGINE CONFIGURATION  (framework-portable; runtime source of truth)
--  Loaded into memory at startup. Seeded once from Scoring Parameters.xlsx.
--  Domains live in engine_lookups (SHARED), not in CHECK constraints.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  engine_apps — consuming-application registry + the SHARED rule-library scope
-- ----------------------------------------------------------------------------
CREATE TABLE dbo.engine_apps (
    app_id        varchar(16)    NOT NULL,        -- 'OTA','SHARED', future 'STK','FFL'
    name          varchar(100)   NOT NULL,
    description   varchar(500)   NULL,
    status        varchar(20)    NOT NULL CONSTRAINT DF_engine_apps_status DEFAULT 'active',
    created_at    datetime2      NOT NULL CONSTRAINT DF_engine_apps_created DEFAULT (getutcdate()),
    CONSTRAINT PK_engine_apps PRIMARY KEY (app_id)
);
GO

-- ----------------------------------------------------------------------------
--  engine_rules — atomic rule definitions (the WHAT)            [§6.1]
-- ----------------------------------------------------------------------------
CREATE TABLE dbo.engine_rules (
    rule_id                  int            NOT NULL IDENTITY(1,1),
    owner_app_id             varchar(16)    NOT NULL,         -- 'SHARED' for cross-app
    rule_key                 varchar(100)   NOT NULL,         -- string handle; bronze references this
    phase                    varchar(40)    NOT NULL,         -- one of the 7 pipeline phases (lookup-validated)
    tier                     varchar(16)    NULL,             -- RAW | DERIVED | COMPUTED
    intent                   varchar(500)   NULL,             -- human description
    condition_expression     varchar(500)   NULL,             -- closed-set expression (§6.3); NULL for pure-formula rules
    formula_ref              varchar(100)   NULL,             -- 'formula:<name>' registry ref
    referenced_named_values  nvarchar(MAX)  NULL,             -- JSON array: named-value inputs (input-catalog validation)
    parameter_schema         nvarchar(MAX)  NULL,             -- JSON: param names+types+bounds the junction must satisfy
    null_semantics           varchar(20)    NULL,             -- FAIL_OPEN | FAIL_CLOSED | SKIP
    enabled                  bit            NOT NULL CONSTRAINT DF_engine_rules_enabled DEFAULT 1,
    created_at               datetime2      NOT NULL CONSTRAINT DF_engine_rules_created DEFAULT (getutcdate()),
    updated_at               datetime2      NULL,
    CONSTRAINT PK_engine_rules PRIMARY KEY (rule_id),
    CONSTRAINT UQ_engine_rules_owner_key UNIQUE (owner_app_id, rule_key),
    CONSTRAINT FK_engine_rules_app FOREIGN KEY (owner_app_id) REFERENCES dbo.engine_apps (app_id),
    CONSTRAINT CK_engine_rules_refvals  CHECK (referenced_named_values IS NULL OR ISJSON(referenced_named_values) = 1),
    CONSTRAINT CK_engine_rules_paramsch CHECK (parameter_schema       IS NULL OR ISJSON(parameter_schema)       = 1)
);
GO
CREATE INDEX ix_engine_rules_phase ON dbo.engine_rules (owner_app_id, phase, enabled);
GO

-- ----------------------------------------------------------------------------
--  engine_strategies — named rule-set + verdict mapping (the WHICH)   [§6.1, §3.8]
--  Per-rule weights/params live on the junction, not here.
-- ----------------------------------------------------------------------------
CREATE TABLE dbo.engine_strategies (
    strategy_id             int            NOT NULL IDENTITY(1,1),
    owner_app_id            varchar(16)    NOT NULL,
    strategy_key            varchar(50)    NOT NULL,          -- 'steady_paycheck','position_health_full',...
    display_name            varchar(100)   NOT NULL,
    consumer_surface        varchar(40)    NOT NULL,          -- SCREENING | POSITION_HEALTH | DIRECTIONAL (lookup-validated)
    description             varchar(MAX)   NULL,
    compatible_structures   nvarchar(MAX)  NULL,              -- JSON array (compatibility map); screening only
    verdict_band_set        nvarchar(MAX)  NOT NULL,          -- JSON: score->verdict/grade bands (EXECUTE/WAIT/PASS or A..F)
    dte_min                 int            NULL,
    dte_max                 int            NULL,
    enabled                 bit            NOT NULL CONSTRAINT DF_engine_strat_enabled DEFAULT 1,
    created_at              datetime2      NOT NULL CONSTRAINT DF_engine_strat_created DEFAULT (getutcdate()),
    updated_at              datetime2      NULL,
    CONSTRAINT PK_engine_strategies PRIMARY KEY (strategy_id),
    CONSTRAINT UQ_engine_strategies_owner_key UNIQUE (owner_app_id, strategy_key),
    CONSTRAINT FK_engine_strategies_app FOREIGN KEY (owner_app_id) REFERENCES dbo.engine_apps (app_id),
    CONSTRAINT CK_engine_strategies_struct CHECK (compatible_structures IS NULL OR ISJSON(compatible_structures) = 1),
    CONSTRAINT CK_engine_strategies_bands  CHECK (ISJSON(verdict_band_set) = 1)
);
GO

-- ----------------------------------------------------------------------------
--  engine_strategy_rule_junction — the HOW (single home of per-strategy config) [§6.2]
-- ----------------------------------------------------------------------------
CREATE TABLE dbo.engine_strategy_rule_junction (
    junction_id        int            NOT NULL IDENTITY(1,1),
    strategy_id        int            NOT NULL,
    rule_id            int            NOT NULL,
    evaluation_order   int            NOT NULL,               -- ordering within the rule's phase
    stop_if_fail       bit            NOT NULL,               -- true -> halt+record; false -> record, hold penalty, continue
    score_penalty      numeric(6,2)   NULL,                   -- held penalty applied in scoring if a non-stopping rule fails
    weight             numeric(7,4)   NULL,                   -- scoring weight; weights sum to 1.0000 per scoring set (§6.6)
    parameters         nvarchar(MAX)  NULL,                   -- JSON: variable per-rule params, validated vs parameter_schema
    terminal_verdict   varchar(32)    NULL,                   -- per (strategy, rule) halt verdict; NULL = no special verdict on halt (§3.8)
    rationale          varchar(1000)  NULL,                   -- one-line why
    enabled            bit            NOT NULL CONSTRAINT DF_engine_junction_enabled DEFAULT 1,
    created_at         datetime2      NOT NULL CONSTRAINT DF_engine_junction_created DEFAULT (getutcdate()),
    updated_at         datetime2      NULL,
    CONSTRAINT PK_engine_junction PRIMARY KEY (junction_id),
    CONSTRAINT UQ_engine_junction UNIQUE (strategy_id, rule_id),
    CONSTRAINT FK_engine_junction_strategy FOREIGN KEY (strategy_id) REFERENCES dbo.engine_strategies (strategy_id),
    CONSTRAINT FK_engine_junction_rule     FOREIGN KEY (rule_id)     REFERENCES dbo.engine_rules (rule_id),
    CONSTRAINT CK_engine_junction_params   CHECK (parameters IS NULL OR ISJSON(parameters) = 1)
);
GO
CREATE INDEX ix_engine_junction_strategy ON dbo.engine_strategy_rule_junction (strategy_id, enabled);
GO
-- evaluation_order uniqueness within (strategy, rule.phase) is enforced at engine
-- load (§6.6), not by a DB constraint — phase lives on the rule, not the junction.

-- ----------------------------------------------------------------------------
--  engine_lookups — generic keyed config sets (phase domain, candidate_type
--                   domain, verdict domain, width tiers, ETF tables, ...)   [§6.1]
-- ----------------------------------------------------------------------------
CREATE TABLE dbo.engine_lookups (
    lookup_id      int            NOT NULL IDENTITY(1,1),
    owner_app_id   varchar(16)    NOT NULL,                   -- 'SHARED' for engine-domain enumerations
    lookup_set     varchar(60)    NOT NULL,                   -- 'pipeline_phases','spread_width_tiers',...
    lookup_key     varchar(100)   NOT NULL,
    payload        nvarchar(MAX)  NOT NULL,                   -- JSON value
    sort_order     int            NULL,
    enabled        bit            NOT NULL CONSTRAINT DF_engine_lookups_enabled DEFAULT 1,
    created_at     datetime2      NOT NULL CONSTRAINT DF_engine_lookups_created DEFAULT (getutcdate()),
    CONSTRAINT PK_engine_lookups PRIMARY KEY (lookup_id),
    CONSTRAINT UQ_engine_lookups UNIQUE (owner_app_id, lookup_set, lookup_key),
    CONSTRAINT FK_engine_lookups_app FOREIGN KEY (owner_app_id) REFERENCES dbo.engine_apps (app_id),
    CONSTRAINT CK_engine_lookups_payload CHECK (ISJSON(payload) = 1)
);
GO
```

---

## 3. Bronze persistence

### 3.1 Engine contract to physical store

The engine emits two logical record streams per run — `CandidateSnapshot` (one per candidate) and `EvaluationDecision` (one per rule evaluation) — through the sink interface (`write_snapshots`, `write_decisions`). The OTA sink lands both streams into a single physical table, `dbo.bronze_evaluations`, discriminated by `record_type`. The physical store is the sink's responsibility (`insight_engine.md` §8); the logical record contract and the sink interface are unchanged. Records carry `source_app_id`, which keeps a shared cross-app bronze zone possible.

```sql
-- ============================================================================
--  BRONZE — single append-only landing table. The OTA sink lands both engine
--  record streams here, discriminated by record_type. No foreign keys.
--  Promoted columns follow the §4.3 filter rule; the rest is payload_json.
-- ============================================================================
CREATE TABLE dbo.bronze_evaluations (
    -- identity / correlation -------------------------------------------------
    record_id          bigint         NOT NULL IDENTITY(1,1),  -- table-assigned surrogate, PK
    record_type        varchar(20)    NOT NULL,                -- 'SNAPSHOT' | 'DECISION'
    run_id             varchar(36)    NOT NULL,                -- one engine.evaluate() call
    snapshot_id        varchar(36)    NOT NULL,                -- sink GUID; unique on SNAPSHOT rows, repeated on its DECISION rows

    -- provenance (stamped on every record) -----------------------------------
    source_app_id      varchar(8)     NOT NULL,                -- 'OTA' | 'STK' | 'FFL'
    config_version     varchar(64)    NOT NULL,
    engine_version     varchar(20)    NULL,
    evaluated_at       datetime2      NOT NULL,
    payload_version    int            NOT NULL,                -- namespaced by candidate_type (SNAPSHOT) / phase (DECISION)

    -- SNAPSHOT-only promoted columns (NULL on DECISION rows) ------------------
    candidate_type     varchar(50)    NULL,                    -- SCREENING | POSITION_HEALTH | DIRECTIONAL
    strategy_key       varchar(50)    NULL,                    -- denormalized (soft)
    symbol             varchar(20)    NULL,
    user_id            varchar(36)    NULL,                    -- data-isolation filter; soft, no FK
    subject_type       varchar(40)    NULL,                    -- POSITION | TRADE_CANDIDATE | DIRECTIONAL_CANDIDATE
    subject_id         varchar(100)   NULL,                    -- positions.position_id / trade_candidates.trade_key (soft)
    final_score        numeric(6,2)   NULL,                    -- null if halted before scoring
    verdict            varchar(32)    NULL,                    -- null if halted before verdict
    terminal_phase     varchar(32)    NULL,                    -- where the candidate exited

    -- DECISION-only promoted columns (NULL on SNAPSHOT rows) ------------------
    rule_key           varchar(100)   NULL,                    -- denormalized rule key (soft)
    phase              varchar(32)    NULL,                    -- gate | scoring | adjustment | verdict
    tier               varchar(16)    NULL,                    -- RAW | DERIVED | COMPUTED
    evaluation_order   int            NULL,
    passed             bit            NULL,
    stop_if_fail       bit            NULL,
    was_terminal       bit            NULL,                    -- did THIS decision halt the pipeline
    score_contribution numeric(8,2)   NULL,                    -- weighted contribution / penalty / adjustment

    -- everything else: decision_reason, params evaluated, formula trace, full named-value set
    payload_json       nvarchar(MAX)  NULL,

    CONSTRAINT PK_bronze_evaluations PRIMARY KEY (record_id),
    CONSTRAINT CK_bronze_evaluations_payload CHECK (payload_json IS NULL OR ISJSON(payload_json) = 1),
    CONSTRAINT CK_bronze_evaluations_type    CHECK (record_type IN ('SNAPSHOT','DECISION'))
);
GO
CREATE INDEX ix_bronze_run            ON dbo.bronze_evaluations (run_id);
CREATE INDEX ix_bronze_snapshot       ON dbo.bronze_evaluations (snapshot_id);
CREATE INDEX ix_bronze_app_type_time  ON dbo.bronze_evaluations (source_app_id, record_type, evaluated_at DESC);
CREATE INDEX ix_bronze_user_time      ON dbo.bronze_evaluations (user_id, evaluated_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX ix_bronze_subject        ON dbo.bronze_evaluations (subject_type, subject_id)   WHERE subject_id IS NOT NULL;
CREATE INDEX ix_bronze_symbol_time    ON dbo.bronze_evaluations (symbol, evaluated_at DESC)  WHERE symbol IS NOT NULL;
CREATE INDEX ix_bronze_rule           ON dbo.bronze_evaluations (rule_key)                    WHERE rule_key IS NOT NULL;
GO

-- ----------------------------------------------------------------------------
--  bronze_payload_contract — self-describing payload registry (read-path aid)
-- ----------------------------------------------------------------------------
CREATE TABLE dbo.bronze_payload_contract (
    contract_id          int            NOT NULL IDENTITY(1,1),
    record_type          varchar(20)    NOT NULL,             -- 'SNAPSHOT' | 'DECISION'
    discriminator_value  varchar(50)    NOT NULL,             -- candidate_type (SNAPSHOT) | phase (DECISION)
    payload_version      int            NOT NULL,
    shape_description    nvarchar(MAX)  NULL,                 -- prose or JSON-schema of payload_json for this combo
    source_app_id        varchar(8)     NULL,
    registered_at        datetime2      NOT NULL CONSTRAINT DF_bronze_contract_reg DEFAULT (getutcdate()),
    CONSTRAINT PK_bronze_payload_contract PRIMARY KEY (contract_id),
    CONSTRAINT UQ_bronze_payload_contract UNIQUE (record_type, discriminator_value, payload_version)
);
GO
```

---

## 4. Relationship to existing tables

Bronze is additive and references existing tables only by soft denormalized key. The engine adds the seven tables above and alters no existing table.

- **`agent_run_log`** records LLM calls; bronze records deterministic engine decisions. The engine completes before any LLM call (`insight_engine.md` principle 2.6), so the order is engine then, on survivors, Claude. A snapshot's `payload_json` may carry the `agent_run_id` of the narrative that followed.
- **`positions`** is the OLTP subject of position-health evaluation. A `POSITION_HEALTH` snapshot sets `subject_type='POSITION'`, `subject_id = position_id`. The Position Monitor Agent writes the engine verdict letter to `positions.health_grade`; the full per-rule trace lives in bronze.
- **`symbol_reference`** is the central symbol reference; bronze `symbol` is a soft denormalized reference to it.
- **App result and cache tables** (`analysis_runs`, `analyzed_trades`, `trade_candidates`, `option_chain_snapshots`, `position_assessments`) remain the application's own. The engine neither reads nor replaces them; a screening or health run may also emit a bronze record for the audit trail.