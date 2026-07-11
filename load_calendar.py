"""
Load calendar data for a given period.

Pipeline: TBU (example: STG_RAW_CALENDAR → STG_CALENDAR (trim) → DELETE + INSERT into warehouse.)

Usage:
    uv run python load_calendar.py --city albany --step None/load_raw/trim/insert
"""

import argparse
import time
import utils.db as db
from utils.detect_format import detect_csv_format
import clickhouse_connect
from datetime import datetime

def get_raw_schema(num_columns: int) -> str:
    base = """
    listing_id UInt64,
    calendar_date Date,
    available LowCardinality(String),
    price Decimal(10,2),
    adjusted_price Decimal(10,2),
    minimum_nights UInt16,
    maximum_nights UInt16
    """
    if num_columns > 7:
        return base + ", EXTRA_PADDING LowCardinality(String)"
    return base


def load_raw(conn: clickhouse_connect.driver.client.Client, city: str, url: str) -> int:
    fmt = detect_csv_format(url)
    raw_table = f"STG_RAW_CALENDAR_{city.upper()}"
    count = db.import_csv(conn, raw_table, url, get_raw_schema(fmt.num_columns), fmt)
    return count


def trim(conn: clickhouse_connect.driver.client.Client, city: str, period: datetime.date) -> None:
    raw_table = f"STG_RAW_CALENDAR_{city.upper()}"
    stg_table = f"STG_CALENDAR_{city.upper()}"

    conn.command(f"DROP TABLE IF EXISTS {stg_table}")

    # check the ratio of 2 columns to ensure remove empty columns. If there are some values in these cols, print on screen to notify users.
    print("Empty ratio of price column: ", conn.command(f"select round(avg(price = defaultValueOfArgumentType(price)), 3) as empty_ratio from {raw_table}"))

    print("Empty ratio of adjusted_price column: ", conn.command(f"select round(avg(adjusted_price = defaultValueOfArgumentType(adjusted_price)), 3) as empty_ratio from {raw_table}"))
    
    # price Decimal(10,2),
    # adjusted_price Decimal(10,2),
    conn.command(f"""CREATE TABLE {stg_table} (
        listing_id UInt64,
        calendar_date Date,
        available LowCardinality(String),
        minimum_nights UInt16,
        maximum_nights UInt16,
        period Date
    )""")

    conn.command(f"""
        INSERT INTO {stg_table}
        SELECT
            listing_id,
            calendar_date,
            available,
            minimum_nights,
            maximum_nights,
            '{period}'
        FROM {raw_table}
    """)

    conn.command(f"DROP TABLE IF EXISTS {raw_table}")

    stg_count = conn.command(f"SELECT COUNT(*) FROM {stg_table}")
    print(f"  STG_CALENDAR: {stg_count:,} rows")


def insert_into_warehouse(conn: clickhouse_connect.driver.client.Client, city: str, period: datetime.date) -> None:
    stg_table = f"STG_CALENDAR_{city.upper()}"

    conn.command(f"ALTER TABLE {db.WAREHOUSE_SCHEMA}.CALENDAR DELETE WHERE period = '{period}'")

    conn.command(f"""
        INSERT INTO {db.WAREHOUSE_SCHEMA}.CALENDAR
        SELECT * FROM {db.STAGING_SCHEMA}.{stg_table}
    """)

    wh_count = conn.command(
        f"SELECT toString(COUNT()) FROM {db.WAREHOUSE_SCHEMA}.CALENDAR")
    print(f"  CALENDAR: {wh_count} rows in warehouse")


def load(conn: clickhouse_connect.driver.client.Client, city: str, url: str, period: datetime.date) -> None:
    count = load_raw(conn, city, url)
    if count == 0:
        print("  No rows loaded")
        return

    trim(conn, city, period)
    insert_into_warehouse(conn, city, period)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CALENDAR data for a given city (example: albany)")
    parser.add_argument("--city", required=True, help="City to load data for")
    parser.add_argument("--step", choices=["load_raw", "trim", "insert"], 
                        help="Run a single step")
    args = parser.parse_args()

    url, period, state, country = db.get_url(city=args.city, file_type="calendar.csv.gz")
    print(f"URL: {url}, period: {period}, neighbourhood_group: {args.city}, {state}, {country}")
    if not url:
        print(f"No CALENDAR URL for city {args.city}")
        return

    conn = db.connect(database=db.STAGING_SCHEMA)
    db.ensure_schemas(conn)
    print(f"Current schema: {db.current_schema(conn)}")

    # Ensure warehouse table exists
    db.create_if_not_exists(conn, f"""
        CREATE TABLE IF NOT EXISTS {db.WAREHOUSE_SCHEMA}.CALENDAR (
            listing_id UInt64,
            calendar_date Date,
            available LowCardinality(String),
            minimum_nights UInt16,
            maximum_nights UInt16,
            period Date
        )
    """)

    print(f"[{args.city}] Loading CALENDAR...")
    start = time.time()

    if not args.step:
        print("load step is not specified, running all steps")
        load(conn, args.city, url, period)
    elif args.step == "load_raw":
        count = load_raw(conn, args.city, url)
        print(f"  Loaded {count} rows into raw table")
    elif args.step == "trim":
        trim(conn, args.city, period)
    elif args.step == "insert":
        insert_into_warehouse(conn, args.city, period=period)

    print(f"[{args.city}] Done in {time.time() - start:.1f}s")

    conn.close()


if __name__ == "__main__":
    main()