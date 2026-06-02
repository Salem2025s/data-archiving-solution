"""Build `processed.dataset_asset_ml` for current Oracle-only V1 scope."""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.dataset_asset_ml WHERE run_id = :run_id"

INSERT_SQL = """
INSERT INTO processed.dataset_asset_ml (
    run_id,
    asset_id,
    source_system,
    asset_type,
    technical_name,
    source_ref,
    field_count,
    nullable_field_count,
    non_nullable_field_count,
    numeric_field_count,
    date_field_count,
    text_field_count,
    large_text_field_count,
    avg_data_length,
    max_data_length,
    row_count,
    size_bytes,
    size_mb,
    has_profile_data,
    column_names_text,
    column_type_signature_text,
    column_value_semantics_text,
    loaded_at
)
WITH field_agg AS (
    SELECT
        df.asset_id,
        COUNT(*)::integer AS field_count,
        COUNT(*) FILTER (WHERE df.nullable_flag = true)::integer AS nullable_field_count,
        COUNT(*) FILTER (WHERE df.nullable_flag = false)::integer AS non_nullable_field_count,
        COUNT(*) FILTER (
            WHERE lower(coalesce(df.data_type, '')) ~ '(number|integer|int|decimal|numeric|float|double)'
        )::integer AS numeric_field_count,
        COUNT(*) FILTER (
            WHERE lower(coalesce(df.data_type, '')) ~ '(date|timestamp|datetime)'
        )::integer AS date_field_count,
        COUNT(*) FILTER (
            WHERE lower(coalesce(df.data_type, '')) ~ '(char|varchar|text|clob)'
        )::integer AS text_field_count,
        COUNT(*) FILTER (
            WHERE lower(coalesce(df.data_type, '')) LIKE '%clob%'
               OR (
                    lower(coalesce(df.data_type, '')) ~ '(char|varchar|text)'
                    AND coalesce(df.data_length, 0) >= 1000
               )
        )::integer AS large_text_field_count,
        AVG(df.data_length)::numeric AS avg_data_length,
        MAX(df.data_length)::bigint AS max_data_length
    FROM processed.dim_field df
    WHERE df.run_id = :run_id
    GROUP BY df.asset_id
),
field_text_agg AS (
        SELECT
                df.asset_id,
                string_agg(df.technical_name, ' | ' ORDER BY df.technical_name) AS column_names_text,
                string_agg(
                        df.technical_name || ':' || coalesce(df.data_type, 'unknown'),
                        ' | ' ORDER BY df.technical_name
                ) AS column_type_signature_text,
                string_agg(
                        df.technical_name || ':' ||
                        CASE
                                WHEN df.technical_name_lc LIKE '%uuid%' OR df.technical_name_lc LIKE '%guid%'
                                        THEN 'technical_identifier'

                                WHEN df.technical_name_lc LIKE '%empl%'
                                    OR df.technical_name_lc LIKE '%employee%'
                                    OR df.technical_name_lc LIKE '%staff%'
                                        THEN 'person_identifier'
                                WHEN df.technical_name_lc LIKE '%user%'
                                    OR df.technical_name_lc LIKE '%login%'
                                    OR df.technical_name_lc LIKE '%account%'
                                        THEN 'user_identifier'
                                WHEN df.technical_name_lc LIKE '%dept%'
                                    OR df.technical_name_lc LIKE '%business_unit%'
                                    OR df.technical_name_lc LIKE '%org%'
                                        THEN 'organization_identifier'

                                WHEN df.technical_name_lc LIKE '%created%'
                                    OR df.technical_name_lc LIKE '%updated%'
                                    OR df.technical_name_lc LIKE '%modified%'
                                        THEN 'technical_timestamp'
                                WHEN df.technical_name_lc LIKE '%start%'
                                    OR df.technical_name_lc LIKE '%end%'
                                        THEN 'date_interval_boundary'
                                WHEN df.technical_name_lc LIKE '%year%'
                                    OR df.technical_name_lc LIKE '%month%'
                                    OR df.technical_name_lc LIKE '%quarter%'
                                        THEN 'date_part'
                                WHEN df.technical_name_lc LIKE '%duration%'
                                    OR df.technical_name_lc LIKE '%delay%'
                                    OR df.technical_name_lc LIKE '%elapsed%'
                                        THEN 'duration'
                                WHEN df.technical_name_lc LIKE '%dt'
                                    OR df.technical_name_lc LIKE '%date%'
                                    OR df.technical_name_lc LIKE '%time%'
                                    OR df.technical_name_lc LIKE '%ts'
                                    OR df.data_type_lc ~ '(date|timestamp|datetime|time)'
                                        THEN 'date_or_timestamp'

                                WHEN df.technical_name_lc LIKE '%amt%'
                                    OR df.technical_name_lc LIKE '%amount%'
                                    OR df.technical_name_lc LIKE '%bal%'
                                    OR df.technical_name_lc LIKE '%salary%'
                                    OR df.technical_name_lc LIKE '%price%'
                                    OR df.technical_name_lc LIKE '%cost%'
                                    OR df.technical_name_lc LIKE '%revenue%'
                                        THEN 'financial_amount'
                                WHEN df.technical_name_lc LIKE '%qty%'
                                    OR df.technical_name_lc LIKE '%count%'
                                    OR df.technical_name_lc LIKE '%nbr%'
                                    OR df.technical_name_lc LIKE '%nb%'
                                        THEN 'quantity'
                                WHEN df.technical_name_lc LIKE '%rate%'
                                    OR df.technical_name_lc LIKE '%pct%'
                                    OR df.technical_name_lc LIKE '%percent%'
                                    OR df.technical_name_lc LIKE '%ratio%'
                                        THEN 'percentage_or_rate'
                                WHEN df.technical_name_lc LIKE '%score%'
                                    OR df.technical_name_lc LIKE '%index%'
                                        THEN 'score'

                                WHEN df.technical_name_lc LIKE '%priority%'
                                    OR df.technical_name_lc LIKE '%severity%'
                                        THEN 'priority_level'
                                WHEN df.technical_name_lc LIKE '%status%'
                                    OR df.technical_name_lc LIKE '%stat%'
                                    OR df.technical_name_lc LIKE '%state%'
                                        THEN 'status'
                                WHEN df.technical_name_lc LIKE '%type%'
                                    OR df.technical_name_lc LIKE '%category%'
                                    OR df.technical_name_lc LIKE '%class%'
                                        THEN 'classification'

                                WHEN df.technical_name_lc LIKE '%email%'
                                    OR df.technical_name_lc LIKE '%mail%'
                                        THEN 'email_address'
                                WHEN df.technical_name_lc LIKE '%phone%'
                                    OR df.technical_name_lc LIKE '%mobile%'
                                    OR df.technical_name_lc LIKE '%tel%'
                                        THEN 'phone_number'
                                WHEN df.technical_name_lc LIKE '%url%'
                                    OR df.technical_name_lc LIKE '%website%'
                                    OR df.technical_name_lc LIKE '%link%'
                                        THEN 'url'

                                WHEN df.technical_name_lc LIKE '%postal%'
                                    OR df.technical_name_lc LIKE '%zipcode%'
                                        THEN 'postal_location'
                                WHEN df.technical_name_lc LIKE '%lat%'
                                        THEN 'geo_latitude'
                                WHEN df.technical_name_lc LIKE '%lon%'
                                    OR df.technical_name_lc LIKE '%lng%'
                                        THEN 'geo_longitude'

                                WHEN df.technical_name_lc LIKE '%firstname%'
                                    OR df.technical_name_lc LIKE '%given_name%'
                                        THEN 'person_first_name'
                                WHEN df.technical_name_lc LIKE '%lastname%'
                                    OR df.technical_name_lc LIKE '%surname%'
                                        THEN 'person_last_name'
                                WHEN df.technical_name_lc LIKE '%fullname%'
                                    OR df.technical_name_lc LIKE '%full_name%'
                                        THEN 'person_full_name'
                                WHEN df.technical_name_lc LIKE '%job%'
                                    OR df.technical_name_lc LIKE '%role%'
                                    OR df.technical_name_lc LIKE '%position%'
                                        THEN 'job_label'

                                WHEN df.technical_name_lc LIKE '%source%'
                                    OR df.technical_name_lc LIKE '%src%'
                                        THEN 'source_system_reference'
                                WHEN df.technical_name_lc LIKE '%target%'
                                    OR df.technical_name_lc LIKE '%tgt%'
                                        THEN 'target_system_reference'
                                WHEN df.technical_name_lc LIKE '%file%'
                                    OR df.technical_name_lc LIKE '%filename%'
                                    OR df.technical_name_lc LIKE '%path%'
                                        THEN 'file_reference'
                                WHEN df.technical_name_lc LIKE '%version%'
                                    OR df.technical_name_lc LIKE '%revision%'
                                        THEN 'version_identifier'
                                WHEN df.technical_name_lc LIKE '%batch%'
                                    OR df.technical_name_lc LIKE '%run%'
                                    OR df.technical_name_lc LIKE '%job%'
                                        THEN 'processing_identifier'

                                WHEN df.technical_name_lc LIKE '%key%'
                                    OR df.technical_name_lc LIKE '%code%'
                                    OR df.technical_name_lc LIKE '%ref%'
                                        THEN 'reference_identifier'
                                WHEN df.technical_name_lc LIKE '%id'
                                    OR df.technical_name_lc LIKE 'id_%'
                                    OR df.technical_name_lc LIKE '%_id'
                                        THEN 'identifier'

                                WHEN df.technical_name_lc LIKE '%descr%'
                                    OR df.technical_name_lc LIKE '%desc%'
                                    OR df.technical_name_lc LIKE '%name%'
                                    OR df.technical_name_lc LIKE '%label%'
                                        THEN 'label'
                                WHEN df.technical_name_lc LIKE '%comment%'
                                    OR df.technical_name_lc LIKE '%remark%'
                                    OR df.technical_name_lc LIKE '%note%'
                                        THEN 'comment_text'
                                WHEN df.technical_name_lc LIKE '%addr%'
                                    OR df.technical_name_lc LIKE '%city%'
                                    OR df.technical_name_lc LIKE '%country%'
                                        THEN 'location_text'
                                ELSE 'other'
                        END,
                        ' | ' ORDER BY df.technical_name
                ) AS column_value_semantics_text
        FROM (
                SELECT
                        asset_id,
                        technical_name,
                        data_type,
                        lower(coalesce(technical_name, '')) AS technical_name_lc,
                        lower(coalesce(data_type, '')) AS data_type_lc
                FROM processed.dim_field
                WHERE run_id = :run_id
        ) df
        GROUP BY df.asset_id
),
profile_ranked AS (
    SELECT
        fp.asset_id,
        fp.row_count,
        fp.size_mb,
        ROW_NUMBER() OVER (
            PARTITION BY fp.asset_id
            ORDER BY fp.snapshot_date DESC NULLS LAST, fp.loaded_at DESC
        ) AS rn
    FROM processed.fact_asset_profile fp
    WHERE fp.run_id = :run_id
),
profile_one AS (
    SELECT
        asset_id,
        row_count,
        size_mb
    FROM profile_ranked
    WHERE rn = 1
)
SELECT
    :run_id AS run_id,
    da.id AS asset_id,
    da.source_system,
    da.asset_type,
    da.technical_name,
    da.source_ref,
    coalesce(fa.field_count, 0) AS field_count,
    coalesce(fa.nullable_field_count, 0) AS nullable_field_count,
    coalesce(fa.non_nullable_field_count, 0) AS non_nullable_field_count,
    coalesce(fa.numeric_field_count, 0) AS numeric_field_count,
    coalesce(fa.date_field_count, 0) AS date_field_count,
    coalesce(fa.text_field_count, 0) AS text_field_count,
    coalesce(fa.large_text_field_count, 0) AS large_text_field_count,
    fa.avg_data_length,
    fa.max_data_length,
    po.row_count,
    CASE
        WHEN po.size_mb IS NOT NULL THEN round(po.size_mb * 1024 * 1024)::bigint
        ELSE NULL::bigint
    END AS size_bytes,
    po.size_mb,
    CASE WHEN po.asset_id IS NOT NULL THEN true ELSE false END AS has_profile_data,
        coalesce(fta.column_names_text, '') AS column_names_text,
        coalesce(fta.column_type_signature_text, '') AS column_type_signature_text,
        coalesce(fta.column_value_semantics_text, '') AS column_value_semantics_text,
    now() AS loaded_at
FROM processed.dim_asset da
LEFT JOIN field_agg fa
  ON fa.asset_id = da.id
LEFT JOIN field_text_agg fta
    ON fta.asset_id = da.id
LEFT JOIN profile_one po
  ON po.asset_id = da.id
WHERE da.run_id = :run_id
  AND da.source_system IN ('oracle', 'peoplesoft')
"""

COUNT_SQL = "SELECT COUNT(*) AS row_count FROM processed.dataset_asset_ml WHERE run_id = :run_id"


def build_dataset_asset_ml(run_id: int) -> int:
    """Build `processed.dataset_asset_ml` for one full-reload run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.dataset_asset_ml for run_id={}", run_id)

        logger.info(
            "Step 1/3 - deleting existing dataset_asset_ml rows for run_id={}",
            run_id,
        )
        postgres_client.execute(DELETE_SQL, {"run_id": run_id})

        logger.info(
            "Step 2/3 - loading Oracle-only dataset_asset_ml rows for run_id={}",
            run_id,
        )
        postgres_client.execute(INSERT_SQL, {"run_id": run_id})

        logger.info("Step 3/3 - counting dataset_asset_ml rows for run_id={}", run_id)
        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0

        logger.info("processed.dataset_asset_ml built: {} row(s)", produced)
        return produced
    except Exception:
        logger.exception("Failed building processed.dataset_asset_ml for run_id={}", run_id)
        raise


def main() -> None:
    """Run local test for `build_dataset_asset_ml`."""
    configure_logging()
    count = build_dataset_asset_ml(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()
