"""
Load listings data for a given period.

Pipeline: TBU (example: STG_RAW_NEIGHBOURHOOD_<CITY> --> STG_NEIGHBOURHOOD_<CITY> (enriched information: neighbourhood_group, period) --> MERGE into warehouse).

STG_RAW_LISTINGS_<CITY> --> STG_NEIGHBOURHOOD_<CITY>

Usage:
    uv run python load_listings.py --city albany --step None/load_raw/enrich/merge

    None is to run the entire pipeline, load_raw is to only load the raw data, enrich is to only enrich the data, and merge is to only merge into the warehouse.
"""

import argparse
import time
import datetime
import clickhouse_connect
from utils import db as db
from utils.detect_format import detect_csv_format

def get_raw_schema(num_columns: int) -> str:
    if num_columns >= 19:
        return f"""id UInt64, 
                    name String,
                    host_id UInt64,
                    host_profile_id UInt64,
                    host_name LowCardinality(String),
                    neighbourhood_group LowCardinality(String),
                    neighbourhood LowCardinality(String),
                    latitude Float32,
                    longitude Float32,
                    room_type LowCardinality(String),
                    price Decimal(10, 2),
                    minimum_nights UInt16,
                    number_of_reviews UInt32,
                    last_review Date,
                    reviews_per_month Float32,
                    calculated_host_listings_count UInt16,
                    availability_365 UInt16,
                    license LowCardinality(String)
                    """
    
    return f"""id UInt64, 
                    name String,
                    host_id UInt64,
                    host_profile_id UInt64,
                    host_name LowCardinality(String),
                    neighbourhood_group LowCardinality(String),
                    neighbourhood LowCardinality(String),
                    latitude Float32,
                    longitude Float32,
                    room_type LowCardinality(String),
                    price Decimal(10, 2),
                    minimum_nights UInt16,
                    number_of_reviews UInt32,
                    last_review Date,
                    reviews_per_month Float32,
                    calculated_host_listings_count UInt16,
                    availability_365 UInt16
                    """

def load_raw(conn: clickhouse_connect.driver.client.Client, city: str, url: str) -> int:
    fmt = detect_csv_format(url)
    raw_table = f"STG_RAW_LISTINGS_{city.upper()}"
    count = db.import_csv(conn, raw_table, url, get_raw_schema(fmt.num_columns), fmt)
    return count

def enrichment(conn: clickhouse_connect.driver.client.Client, city: str, period: datetime.date) -> None:
    raw_table = f"STG_RAW_LISTINGS_{city.upper()}"
    stg_table = f"STG_LISTINGS_{city.upper()}"

    conn.command(f"DROP TABLE IF EXISTS {stg_table}")

    # check the ratio of 3 columns to ensure remove empty columns. If there are some values in these cols, print on screen to notify users.
    print("Empty ratio of neighbourhood_group column: ", conn.command(f"select round(avg(neighbourhood_group = defaultValueOfArgumentType(neighbourhood_group)), 3) as empty_ratio from {raw_table}"))

    print("Empty ratio of price column: ", conn.command(f"select round(avg(price = defaultValueOfArgumentType(price)), 3) as empty_ratio from {raw_table}"))
                                                                                  
    print("Empty ratio of license column: ", conn.command(f"select round(avg(license = defaultValueOfArgumentType(license)), 3) as empty_ratio from {raw_table}"))

    # columns to remove in staging table:
    # neighbourhood_group LowCardinality(String),
    # price Decimal(10, 2),
    # license LowCardinality(String)
    # add one column: period
    conn.command(f"""CREATE TABLE {stg_table} (
        listing_id UInt64, 
        listing_description String,
        host_id UInt64,
        host_profile_id UInt64,
        host_name LowCardinality(String),
        neighbourhood_id UUID,
        latitude Float32,
        longitude Float32,
        room_type LowCardinality(String),
        minimum_nights UInt16,
        number_of_reviews UInt32,
        last_review Date,
        reviews_per_month Float32,
        calculated_host_listings_count UInt16,
        availability_365 UInt16,
        period Date
    )""")



    conn.command(f"""
        INSERT INTO {stg_table}
        SELECT
            r.id as listing_id,
            r.name as listing_description,
            r.host_id as host_id,
            r.host_profile_id as host_profile_id,
            r.host_name as host_name,
            wh_neighobourhoods.neighbourhood_id,
            r.latitude as latitude,
            r.longitude as longitude,
            r.room_type as room_type,
            r.minimum_nights as minimum_nights,
            r.number_of_reviews as number_of_reviews,
            r.last_review as last_review,
            r.reviews_per_month as reviews_per_month,
            r.calculated_host_listings_count as calculated_host_listings_count,
            r.availability_365 as availability_365,
            '{period}' AS period
        FROM {raw_table} as r
        JOIN {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS as wh_neighobourhoods
        ON r.neighbourhood = wh_neighobourhoods.neighbourhood
        WHERE wh_neighobourhoods.city = '{city}';
    """)

    conn.command(f"DROP TABLE IF EXISTS {raw_table}")

    stg_count = conn.command(f"SELECT COUNT(*) FROM {stg_table}")
    print(f"  STG_LISTINGS: {stg_count:,} rows")

def merge_into_warehouse(conn: clickhouse_connect.driver.client.Client, city: str) -> None:
    stg_table = f"STG_LISTINGS_{city.upper()}"
    conn.command(f"""
         INSERT INTO {db.WAREHOUSE_SCHEMA}.LISTINGS
         SELECT * FROM {stg_table}
    """)

    wh_count = conn.command(f"SELECT COUNT(*) FROM {db.WAREHOUSE_SCHEMA}.LISTINGS")
    print(f"  LISTINGS: {wh_count:,} rows in warehouse")

def load(conn: clickhouse_connect.driver.client.Client, city: str, url: str, period: datetime.date) -> None:
    count = load_raw(conn, city, url)
    if count == 0:
        print("  No rows loaded")
        return

    enrichment(conn, city, period)
    merge_into_warehouse(conn, city)

def main() -> None:
    parser = argparse.ArgumentParser(description="Load LISTINGS data for a given city (example: albany)")
    parser.add_argument("--city", required=True, help="City to load data for")
    parser.add_argument("--step", choices=["load_raw", "enrich", "merge"],
                        help="Run a single step")
    args = parser.parse_args()

    url, period, state, country = db.get_url(city=args.city, file_type="listings.csv")
    print(f"URL: {url}, period: {period}, neighbourhood_group: {args.city}, {state}, {country}")
    if not url:
        print(f"No LISTINGS URL for city {args.city}")
        return

    conn = db.connect(database=db.STAGING_SCHEMA)
    db.ensure_schemas(conn)
    print(f"Current schema: {db.current_schema(conn)}")

    # Ensure warehouse table exists
    db.create_if_not_exists(conn, f"""
        CREATE TABLE IF NOT EXISTS {db.WAREHOUSE_SCHEMA}.LISTINGS (
            listing_id UInt64, 
            listing_description String,
            host_id UInt64,
            host_profile_id UInt64,
            host_name LowCardinality(String),
            neighbourhood_id UUID,
            latitude Float32,
            longitude Float32,
            room_type LowCardinality(String),
            minimum_nights UInt16,
            number_of_reviews UInt32,
            last_review Date,
            reviews_per_month Float32,
            calculated_host_listings_count UInt16,
            availability_365 UInt16,
            period Date
        )
        ENGINE = ReplacingMergeTree(period)
        ORDER BY listing_id
    """)

    print(f"[{args.city}] Loading LISTINGS...")
    start = time.time()

    if not args.step:
        print("load step is not specified, running all steps")
        load(conn, args.city, url, period)
    elif args.step == "load_raw":
        count = load_raw(conn, args.city, url)
        print(f"  Loaded {count} rows into raw table")
    elif args.step == "enrich":
        enrichment(conn, args.city, period)
    elif args.step == "merge":
        merge_into_warehouse(conn, args.city)

    print(f"[{args.city}] Done in {time.time() - start:.1f}s")

    conn.close()


if __name__ == "__main__":
    main()