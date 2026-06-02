-- Create admin schema tables for pipeline orchestration

CREATE TABLE IF NOT EXISTS admin.pipeline_run (
    id SERIAL PRIMARY KEY,
    flow_name VARCHAR(255) NOT NULL,
    run_type VARCHAR(50) NOT NULL,
    source_system VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'running',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_run_flow_name 
    ON admin.pipeline_run(flow_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_status 
    ON admin.pipeline_run(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_created_at 
    ON admin.pipeline_run(created_at DESC);
