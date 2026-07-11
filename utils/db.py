"""
Shared database utilities for Inside Airbnb ingestion.

Provides connection management and import helpers.
"""

import json
import ssl

import clickhouse_connect

from utils.connection_info import get_config
from utils.detect_format import CsvFormat
from datetime import datetime


STAGING_SCHEMA = "INSIDE_AIRBNB_STAGING"
WAREHOUSE_SCHEMA = "INSIDE_AIRBNB_BOOKING"
URLS_FILE = "code/data/latest_airbnb_urls.json" # Path to the JSON file containing Airbnb URLs


def connect(database: str = 'default') -> clickhouse_connect.driver.client.Client:
    # cfg = get_config()
    conn = clickhouse_connect.get_client(database=database)
    return conn


def create_if_not_exists(conn: clickhouse_connect.driver.client.Client, sql: str) -> None:
    """Run a CREATE IF NOT EXISTS query, ignoring concurrent-creation conflicts."""
    try:
        conn.command(sql)
    except clickhouse_connect.driver.exceptions.Error:
        pass  # object already exists (concurrent creation race)


def ensure_schemas(conn: clickhouse_connect.driver.client.Client) -> None:
    create_if_not_exists(conn, f"CREATE SCHEMA IF NOT EXISTS {STAGING_SCHEMA};")
    create_if_not_exists(conn, f"CREATE SCHEMA IF NOT EXISTS {WAREHOUSE_SCHEMA};")
    

def current_schema(conn: clickhouse_connect.driver.client.Client):
    return conn.command("SELECT currentDatabase()")

def import_csv(
    conn: clickhouse_connect.driver.client.Client,
    table_name: str,
    csv_url: str,
    columns_def: str,
    fmt: CsvFormat,
) -> int:
    conn.command(f"DROP TABLE IF EXISTS {table_name}")
    conn.command(f"CREATE TABLE {table_name} ({columns_def})")

    conn.command(f"""
        INSERT INTO {table_name}
        SELECT * FROM url('{csv_url}', 'CSV')
        settings input_format_csv_skip_first_lines={fmt.skip};
    """)

    count = conn.command(f"SELECT COUNT(*) FROM {table_name}")
    return count

def get_url(city: str, file_type: str) -> str:
    with open(URLS_FILE) as f:
        data = json.load(f)
    
    matches = [m for m in data if m['city'] == city and m['name'] == file_type]

    if not matches:
        raise ValueError(f"City {city} or file type {file_type} not found in {URLS_FILE}")

    date =  datetime.strptime(matches[0]['date'], "%Y-%m-%d").date()

    return matches[0]['url'], date, matches[0]['state'], matches[0]['country']
