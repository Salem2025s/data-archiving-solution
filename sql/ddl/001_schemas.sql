-- Create all required schemas for the pfe-data-ia pipeline

CREATE SCHEMA IF NOT EXISTS admin;
CREATE SCHEMA IF NOT EXISTS raw_oracle;
CREATE SCHEMA IF NOT EXISTS processed;
CREATE SCHEMA IF NOT EXISTS serving;

GRANT USAGE ON SCHEMA admin TO postgres;
GRANT USAGE ON SCHEMA raw_oracle TO postgres;
GRANT USAGE ON SCHEMA processed TO postgres;
GRANT USAGE ON SCHEMA serving TO postgres;
