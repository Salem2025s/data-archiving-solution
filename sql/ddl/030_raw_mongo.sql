-- V1 raw_mongo schema aligned with current extract/load/transform code

CREATE TABLE IF NOT EXISTS raw_mongo.collection_inventory (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    collection_name TEXT,
    db_name TEXT,
    document_count BIGINT,
    avg_obj_size_bytes BIGINT,
    storage_size_bytes BIGINT,
    total_index_size_bytes BIGINT,
    sample_document JSONB,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.metadatastable (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    name TEXT,
    object_md TEXT,
    module_md TEXT,
    status TEXT,
    effective_date TIMESTAMPTZ,
    add_by TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    updated_by TEXT,
    date_synch_md TIMESTAMPTZ,
    columns_count BIGINT,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.fields (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    name TEXT,
    object_md TEXT,
    label TEXT,
    length BIGINT,
    data_type TEXT,
    scale BIGINT,
    status TEXT,
    property_type TEXT,
    type TEXT,
    confidentiality TEXT,
    disponibility TEXT,
    integrity TEXT,
    traceability TEXT,
    effective_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.datalineage (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    name TEXT,
    status TEXT,
    type TEXT,
    effective_date TIMESTAMPTZ,
    checked_no BIGINT,
    checked_mod BIGINT,
    family_mod BIGINT,
    checked_high BIGINT,
    family_high BIGINT,
    checked_crit BIGINT,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.business_term (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    business_id TEXT,
    cid TEXT,
    vid TEXT,
    name TEXT,
    status TEXT,
    terms_count BIGINT,
    metadatas_count BIGINT,
    tables_count BIGINT,
    confidentialite TEXT,
    disponibilite TEXT,
    integrite TEXT,
    tracabilite TEXT,
    effective_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.glossary (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    name TEXT,
    type TEXT,
    status TEXT,
    effective_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    property_type TEXT,
    module_group_count BIGINT,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.classification_definition (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    name TEXT,
    type TEXT,
    status TEXT,
    effective_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    property_type TEXT,
    module_group_count BIGINT,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.archlog_purge (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    systnaps_archid TEXT,
    name_table TEXT,
    count_src BIGINT,
    count_arch BIGINT,
    count_csv BIGINT,
    count_bad BIGINT,
    count_temp BIGINT,
    count_purge BIGINT,
    base TEXT,
    campaign TEXT,
    time_save_csv TEXT,
    time_load_temp TEXT,
    time_purge TEXT,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE TABLE IF NOT EXISTS raw_mongo.project_catalog (
    run_id INTEGER NOT NULL,
    source_doc_id TEXT NOT NULL,
    project_ref TEXT,
    name_model TEXT,
    name_app TEXT,
    business TEXT,
    document_json JSONB,
    document_hash VARCHAR(64),
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source_doc_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_mongo_collection_inventory_run_id
    ON raw_mongo.collection_inventory (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_metadatastable_run_id
    ON raw_mongo.metadatastable (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_fields_run_id
    ON raw_mongo.fields (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_datalineage_run_id
    ON raw_mongo.datalineage (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_business_term_run_id
    ON raw_mongo.business_term (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_glossary_run_id
    ON raw_mongo.glossary (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_classification_definition_run_id
    ON raw_mongo.classification_definition (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_archlog_purge_run_id
    ON raw_mongo.archlog_purge (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_mongo_project_catalog_run_id
    ON raw_mongo.project_catalog (run_id);
