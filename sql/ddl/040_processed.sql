-- V1 processed schema aligned with current build_* scripts

CREATE TABLE IF NOT EXISTS processed.dim_asset (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    source_system TEXT,
    asset_type TEXT,
    technical_name TEXT,
    business_name TEXT,
    schema_name TEXT,
    owner_name TEXT,
    description TEXT,
    status TEXT,
    source_ref TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.dim_field (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT,
    technical_name TEXT,
    business_name TEXT,
    data_type TEXT,
    data_length BIGINT,
    nullable_flag BOOLEAN,
    source_ref TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.bridge_asset_term (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT,
    term_name TEXT,
    term_source TEXT,
    definition TEXT,
    domain_name TEXT,
    confidence_score NUMERIC,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.fact_asset_profile (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT,
    snapshot_date DATE,
    row_count BIGINT,
    size_mb NUMERIC,
    column_count INTEGER,
    index_count INTEGER,
    last_analyzed TIMESTAMP,
    source_profile_json JSONB,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.fact_lineage_edge (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    source_asset_id BIGINT,
    source_field_id BIGINT,
    target_asset_id BIGINT,
    target_field_id BIGINT,
    lineage_type TEXT,
    transformation_rule TEXT,
    lineage_level INTEGER,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.fact_archiving_event (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT,
    event_date DATE,
    event_type TEXT,
    rows_affected BIGINT,
    volume_mb NUMERIC,
    job_name TEXT,
    status TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.features_asset (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT,
    snapshot_date DATE,
    row_count BIGINT,
    size_mb NUMERIC,
    column_count INTEGER,
    index_count INTEGER,
    lineage_in_count INTEGER,
    lineage_out_count INTEGER,
    term_count INTEGER,
    purge_event_count INTEGER,
    total_purged_rows BIGINT,
    archival_candidate_score NUMERIC,
    roi_score NUMERIC,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.dataset_asset_ml (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT,
    source_system TEXT,
    asset_type TEXT,
    technical_name TEXT,
    source_ref TEXT,
    field_count INTEGER,
    nullable_field_count INTEGER,
    non_nullable_field_count INTEGER,
    numeric_field_count INTEGER,
    date_field_count INTEGER,
    text_field_count INTEGER,
    large_text_field_count INTEGER,
    avg_data_length NUMERIC,
    max_data_length BIGINT,
    row_count BIGINT,
    size_bytes BIGINT,
    size_mb NUMERIC,
    has_profile_data BOOLEAN,
    column_names_text TEXT,
    column_type_signature_text TEXT,
    column_value_semantics_text TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processed_dim_asset_run_id
    ON processed.dim_asset (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_dim_asset_run_id_id
    ON processed.dim_asset (run_id, id);
CREATE INDEX IF NOT EXISTS idx_processed_dim_asset_source_ref
    ON processed.dim_asset (run_id, source_ref);

CREATE INDEX IF NOT EXISTS idx_processed_dim_field_run_id
    ON processed.dim_field (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_dim_field_asset_id
    ON processed.dim_field (run_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_processed_bridge_run_id
    ON processed.bridge_asset_term (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_bridge_asset_id
    ON processed.bridge_asset_term (run_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_processed_profile_run_id
    ON processed.fact_asset_profile (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_profile_asset_id
    ON processed.fact_asset_profile (run_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_processed_lineage_run_id
    ON processed.fact_lineage_edge (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_lineage_source_asset
    ON processed.fact_lineage_edge (run_id, source_asset_id);
CREATE INDEX IF NOT EXISTS idx_processed_lineage_target_asset
    ON processed.fact_lineage_edge (run_id, target_asset_id);

CREATE INDEX IF NOT EXISTS idx_processed_archiving_run_id
    ON processed.fact_archiving_event (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_archiving_asset_id
    ON processed.fact_archiving_event (run_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_processed_features_run_id
    ON processed.features_asset (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_features_asset_id
    ON processed.features_asset (run_id, asset_id);

CREATE INDEX IF NOT EXISTS idx_processed_dataset_ml_run_id
    ON processed.dataset_asset_ml (run_id);
CREATE INDEX IF NOT EXISTS idx_processed_dataset_ml_asset_id
    ON processed.dataset_asset_ml (run_id, asset_id);
