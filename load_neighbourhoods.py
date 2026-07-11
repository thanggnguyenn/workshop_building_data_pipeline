"""
Load neighbourhood data for a given period.

Pipeline: STG_RAW_NEIGHBOURHOOD_<CITY> --> STG_NEIGHBOURHOOD_<CITY> (enriched information: neighbourhood_group, period) --> MERGE into warehouse.

Usage:
    uv run python load_neighbourhoods.py --city albany --step None/load_raw/enrich/merge

    None is to run the entire pipeline, load_raw is to only load the raw data, enrich is to only enrich the data, and merge is to only merge into the warehouse.
"""

import argparse
import time
import datetime

import clickhouse_connect

from utils import db as db
from utils.detect_format import detect_csv_format


def get_raw_schema(num_columns: int) -> str:
    if num_columns >= 2:
        return "neighbourhood_group String, neighbourhood String"
    return "neighbourhood String"


def load_raw(conn: clickhouse_connect.driver.client.Client, city: str, url: str) -> int:
    fmt = detect_csv_format(url)
    raw_table = f"STG_RAW_NEIGHBOURHOOD_{city.upper()}"
    count = db.import_csv(conn, raw_table, url, get_raw_schema(fmt.num_columns), fmt)
    return count


def enrichment(conn: clickhouse_connect.driver.client.Client, city: str, state: str, country: str, period: datetime.date) -> None:
    raw_table = f"STG_RAW_NEIGHBOURHOOD_{city.upper()}"
    stg_table = f"STG_NEIGHBOURHOOD_{city.upper()}"

    conn.command(f"DROP TABLE IF EXISTS {stg_table}")
    conn.command(f"""CREATE TABLE {stg_table} (
        neighbourhood_group LowCardinality(String),
        neighbourhood LowCardinality(String),
        city LowCardinality(String),
        state LowCardinality(String),
        country LowCardinality(String),
        period Date
    )""")

    conn.command(f"""
        INSERT INTO {stg_table}
        SELECT 
            neighbourhood_group,
            neighbourhood,
            '{city}' as city,
            '{state}' as state,
            '{country}' as country,
            '{period}' AS period
        FROM {raw_table}
        WHERE neighbourhood != '';
    """)

    conn.command(f"DROP TABLE IF EXISTS {raw_table}")

    stg_count = conn.command(f"SELECT COUNT(*) FROM {stg_table}")
    print(f"  STG_NEIGHBOURHOOD: {stg_count:,} rows")


def merge_into_warehouse(conn: clickhouse_connect.driver.client.Client, city: str) -> None:
    stg_table = f"STG_NEIGHBOURHOOD_{city.upper()}"

    conn.command(f"""
        INSERT INTO {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS (neighbourhood_id, neighbourhood_group, neighbourhood, city, state, country, period)
        SELECT 
            generateUUIDv4() AS neighbourhood_id,
            *
        FROM {db.STAGING_SCHEMA}.{stg_table}
    """)

    wh_count = conn.command(f"SELECT COUNT(*) FROM {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS")
    print(f"  NEIGHBOURHOODS: {wh_count:,} rows in warehouse")


def load(conn: clickhouse_connect.driver.client.Client, city: str, state: str, country: str, url: str, period: datetime.date) -> None:
    count = load_raw(conn, city, url)
    if count == 0:
        print("  No rows loaded")
        return

    enrichment(conn, city, state, country, period)
    merge_into_warehouse(conn, city)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load NEIGHBOURHOOD data for a given city (example: albany)")
    parser.add_argument("--city", required=True, help="City to load data for")
    parser.add_argument("--step", choices=["load_raw", "enrich", "merge"],
                        help="Run a single step")
    args = parser.parse_args()

    url, period, state, country = db.get_url(city=args.city, file_type="neighbourhoods.csv")
    print(f"URL: {url}, period: {period}, neighbourhood_group: {state}, {country}")
    if not url:
        print(f"No NEIGHBOURHOOD URL for city {args.city}")
        return

    conn = db.connect(database=db.STAGING_SCHEMA)
    db.ensure_schemas(conn)
    print(f"Current schema: {db.current_schema(conn)}")

    # Ensure warehouse table exists
    db.create_if_not_exists(conn, f"""
        CREATE TABLE IF NOT EXISTS {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS (
            neighbourhood_id UUID,
            neighbourhood_group LowCardinality(String),
            neighbourhood LowCardinality(String),
            city LowCardinality(String),
            state LowCardinality(String),
            country LowCardinality(String),
            period Date
        )
        ENGINE = ReplacingMergeTree(period)
        ORDER BY (neighbourhood, neighbourhood_group, city)
    """)

    print(f"[{args.city}] Loading NEIGHBOURHOOD...")
    start = time.time()

    if not args.step:
        load(conn, args.city, state, country, url, period)
    elif args.step == "load_raw":
        count = load_raw(conn, args.city, url)
        print(f"  Loaded {count} rows into raw table")
    elif args.step == "enrich":
        enrichment(conn, args.city, state, country, period)
    elif args.step == "merge":
        merge_into_warehouse(conn, args.city)

    print(f"[{args.city}] Done in {time.time() - start:.1f}s")

    conn.close()


if __name__ == "__main__":
    main()