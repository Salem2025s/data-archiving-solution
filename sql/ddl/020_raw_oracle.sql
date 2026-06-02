-- V1 raw_oracle schema aligned with current extract/load/transform code

CREATE TABLE IF NOT EXISTS raw_oracle.record_catalog (
    run_id INTEGER NOT NULL,
    recname TEXT NOT NULL,
    recdescr TEXT,
    rectype TEXT,
    sqltablename_raw TEXT,
    physical_table_name TEXT,
    mapping_source TEXT,
    oracle_owner TEXT,
    oracle_table_name TEXT,
    table_exists_flag INTEGER,
    parentrecname TEXT,
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, recname)
);

CREATE TABLE IF NOT EXISTS raw_oracle.table_catalog (
    run_id INTEGER NOT NULL,
    owner TEXT,
    table_name TEXT,
    tablespace_name TEXT,
    num_rows BIGINT,
    blocks BIGINT,
    avg_row_len BIGINT,
    last_analyzed TIMESTAMP,
    last_modified TIMESTAMP,
    referenced_by_count BIGINT,
    temporary_flag TEXT,
    partitioned_flag TEXT,
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, owner, table_name)
);

CREATE TABLE IF NOT EXISTS raw_oracle.column_catalog (
    run_id INTEGER NOT NULL,
    recname TEXT,
    physical_table_name TEXT,
    column_id INTEGER,
    column_name TEXT,
    data_type TEXT,
    data_length BIGINT,
    data_precision BIGINT,
    data_scale BIGINT,
    nullable_flag TEXT,
    num_distinct BIGINT,
    num_nulls BIGINT,
    histogram TEXT,
    fieldnum BIGINT,
    useedit BIGINT,
    recname_parent TEXT,
    fieldtype BIGINT,
    ps_field_length BIGINT,
    decimalpos BIGINT,
    field_descrlong TEXT,
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, recname, column_id, column_name)
);

CREATE TABLE IF NOT EXISTS raw_oracle.index_catalog (
    run_id INTEGER NOT NULL,
    recname TEXT,
    indexid TEXT,
    uniqueness_flag TEXT,
    field_position BIGINT,
    fieldname TEXT,
    ascdesc TEXT,
    row_hash VARCHAR(64),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, recname, indexid, field_position, fieldname)
);

CREATE INDEX IF NOT EXISTS idx_raw_oracle_record_run_id
    ON raw_oracle.record_catalog (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_oracle_record_parentrecname
    ON raw_oracle.record_catalog (run_id, parentrecname);
CREATE INDEX IF NOT EXISTS idx_raw_oracle_table_run_id
    ON raw_oracle.table_catalog (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_oracle_column_run_id
    ON raw_oracle.column_catalog (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_oracle_column_table
    ON raw_oracle.column_catalog (run_id, physical_table_name);
CREATE INDEX IF NOT EXISTS idx_raw_oracle_column_recname_parent
    ON raw_oracle.column_catalog (run_id, recname_parent);
CREATE INDEX IF NOT EXISTS idx_raw_oracle_index_run_id
    ON raw_oracle.index_catalog (run_id);

-- Migration idempotente pour installations existantes
ALTER TABLE raw_oracle.record_catalog
    ADD COLUMN IF NOT EXISTS parentrecname TEXT;

ALTER TABLE raw_oracle.column_catalog
    ADD COLUMN IF NOT EXISTS useedit BIGINT;
ALTER TABLE raw_oracle.column_catalog
    ADD COLUMN IF NOT EXISTS recname_parent TEXT;

ALTER TABLE raw_oracle.table_catalog
    ADD COLUMN IF NOT EXISTS last_modified TIMESTAMP;
ALTER TABLE raw_oracle.table_catalog
    ADD COLUMN IF NOT EXISTS referenced_by_count BIGINT;
