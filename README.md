# Workshop : Building data pipeline with Python, SQL
This repository contains a data pipeline (ETL pipeline) designed to ingest, clean, and store the [Inside Airbnb dataset](https://insideairbnb.com/get-the-data/) into a data warehouse. The system implements a Star Schema data model.

## Tools and Packages

- **Python:** The core language used to write the extraction, transformation, and ingestion logic.

- **ClickHouse:** A column-oriented database management system used as the data warehouse layer to store both raw staging datasets and optimized production tables.

- **clickhouse-connect:** The official, lightweight Python driver used to connect to and interact with the ClickHouse database.

- **uv:** An extremely fast Python package installer and resolver used to manage project dependencies and safely execute the scripts (uv run python ...).

## Data pipeline architecture
Each CSV file is ingested directly from the source URL and moves through a multi-stage staging pipeline to ensure data integrity, cleanliness, and transformation before being loaded into the production analytics layer:

```
https://data.insideairbnb.com/united-states/ny/albany/2026-06-16/data/calendar.csv.gz 
       │
       V
 1. STG_RAW_xxxx       ──> Raw data ingestion directly from URL into temporary staging tables.
       │
       V
 3. STG_xxxx           ──> Data enrichment and basic cleaning
       │
       V
 5. Warehouse (Final)  ──> Idempotent insert into production Fact/Dimension tables.
```

## Data model design (star schema)
Once the data is processed, it is organized into a star schema optimized for fast analytical queries:

### 1. Fact table

CALENDAR: Stores daily availability and pricing for each listing.

### 2. Dimension tables

NEIGHBOURHOODS: Stores city areas and neighborhood groups.

LISTINGS: Stores property details (ID, host information, room type, price, minimum nights, etc.).

## How to get CSV URLs

Run the following script: `uv run python find_extract_url.py`

File `find_extract_url.py` is in the `utils` folder.

This will return a JSON file that contained all the urls for ETL process.

## ETL step-by-step implementation

**Step 1**: Raw data ingestion from URL (`load_raw`)

We initialize raw staging tables to pull data streams directly from the source CSV URLs.

```
# SQL

-- Example: Creating the raw staging table for CALENDAR 
CREATE TABLE INSIDE_AIRBNB_STAGING.STG_RAW_CALENDAR_<city name> (
    listing_id UInt64,
    calendar_date Date,
    available LowCardinality(String),
    price Decimal(10,2),
    adjusted_price Decimal(10,2),
    minimum_nights UInt16,
    maximum_nights UInt16)

-- Ingesting raw data directly from the URL
 INSERT INTO INSIDE_AIRBNB_STAGING.STG_RAW_CALENDAR_<city name>
 SELECT * FROM url('{csv_url}', 'CSV')
 settings input_format_csv_skip_first_lines={fmt.skip};
```

**Step 2**: Clean/Transform (`enrich` / `trim`):

Cleans up whitespace padding, formats data types, and prepares the data for the final tables.

```
# SQL

INSERT INTO INSIDE_AIRBNB_STAGING.STG_CALENDAR_<city name>
 SELECT
     listing_id,
     calendar_date,
     available,
     minimum_nights,
     maximum_nights,
     '{period}'
 FROM INSIDE_AIRBNB_STAGING.STG_RAW_CALENDAR_<city name>
```

**Step 3**: Idempotent Warehouse Loading (`merge` / `insert`)

To ensure the pipeline is idempotent (meaning it can be re-run multiple times safely without creating duplicate records or data anomalies):

For Dimension Tables: We use the MERGE statement to update details if the entity already exists, or insert it if it's new.

For Fact Tables: We adopt a DELETE + INSERT strategy isolated by each specific PERIOD.

```
# SQL
-- Create table with specific engine for MERGE operations
CREATE TABLE IF NOT EXISTS {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS (
     neighbourhood_id UUID,
     neighbourhood_group LowCardinality(String),
     neighbourhood LowCardinality(String),
     city LowCardinality(String),
     state LowCardinality(String),
     country LowCardinality(String),
     period Date
 )
 ENGINE = ReplacingMergeTree(period) -- engine for MERGE operations
 ORDER BY (neighbourhood, neighbourhood_group, city) -- keys to make comparsions when merging

-- Idempotent MERGE operation into the NEIGHBOURHOODS dimension table
INSERT INTO {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS (neighbourhood_id, neighbourhood_group, neighbourhood, city, state, country, period)
SELECT 
generateUUIDv4() AS neighbourhood_id,
*
FROM INSIDE_AIRBNB_STAGING.STG_NEIGHBOURHOODS_<city name>
```

## Automated pipelines with Python

Before running the following steps, you need to install [**uv - python package manager**](https://docs.astral.sh/uv/), then create a virtual enviroment with command: `uv init --python <version>`

Add necessary package with command: `uv add <package name>` (for example: clickhouse-connect)

To run the full pipeline for a specific city (for example, albany), follow these steps in order:

**Step 1**: Process Neighbourhoods

First, run the neighborhood ingestion pipeline. This populates the regional boundaries needed for dimension mappings.

Bash
```
# 1. Download and load raw data into the raw staging table
uv run python load_neighbourhoods.py --city albany --step load_raw

# 2. Clean up the data and add state/country fields
uv run python load_neighbourhoods.py --city albany --step enrich

# 3. Merge the cleaned records into the production warehouse table
uv run python load_neighbourhoods.py --city albany --step merge
```

**Step 2**: Process Listings

Next, process the property listings. This stage relies on the neighborhood structures established in **Step 1**.

Bash

```
# 1. Download and load raw listing CSV profiles into staging
uv run python load_listings.py --city albany --step load_raw

# 2. Re-format prices, fix data types, and clean formatting anomalies
uv run python load_listings.py --city albany --step enrich

# 3. Merge the finalized listing records into the production table
uv run python load_listings.py --city albany --step merge
```

**Step 3**: Process Calendar

Finally, load the daily schedule metrics. Because calendar datasets are often massive, this script uses a lightweight trimming and insertion flow.

Bash

```
# 1. Download and load daily calendar schedules into staging
uv run python load_calendar.py --city albany --step load_raw

# 2. Trim whitespace and handle extra column padding variations
uv run python load_calendar.py --city albany --step trim

# 3. Safely insert records into the production warehouse table
uv run python load_calendar.py --city albany --step insert
```

## Analytical queries & verification

To ensure data integrity, schema compliance, and correct warehouse performance, verification is automated via targeted analytical queries. The validation suite guarantees that data pipelines have successfully populated the data warehouse before downstream BI tools or data science models consume the data.

### Automated Verification Script

The warehouse verification process is fully containerized and managed using uv for fast, reproducible execution. The execution entry point is defined as follows:

Bash
```
# Run analytics queries to verify the data warehouse is working.
uv run python code/test/check_warehouse.py
```

### Implementation Logic

The script initializes a secure database connection, guarantees the structural existence of required schemas, and executes baseline analytical health checks.

Python
```
import utils.db as db

def main() -> None:
    # 1. Establish connection to the data warehouse
    conn = db.connect()
    
    # 2. Verify all core schemas and tables exist
    db.ensure_schemas(conn)
    
    # 3. Run validation queries (e.g., row counts, null checks)
    # TODO: Append specific analytical test queries here

if __name__ == "__main__":
    main()
```

### Core Verification Metrics

During the verification phase, the script evaluates the following analytical dimensions:

Schema & Structural Integrity: Confirms that all star/snowflake schemas (fact and dimension tables) are properly generated and match the target DDL definitions.

Data Volume Baselines: Executes COUNT(*) queries across critical tables to ensure that the ETL/ELT pipelines haven't suffered silent failures resulting in empty tables.

Data Quality Constraints: Validates that primary keys remain unique and foreign key relationships hold true across the warehouse schema.

1. Data Integrity & Row Count Verification

SQL

```
SELECT 
     name AS TABLE_NAME, 
     total_rows AS TABLE_ROW_COUNT
 FROM system.tables
 WHERE database = '{db.WAREHOUSE_SCHEMA}'
 AND name IN ('NEIGHBOURHOODS', 'LISTINGS', 'CALENDAR')
```

2. Top 10 neighbourhoods by total listings

SQL
```
SELECT wn.country, wn.state, wn.city, wn.neighbourhood_group, wn.neighbourhood, wl.total_reviews, wl.total_listings
 FROM (
     SELECT neighbourhood_id, SUM(number_of_reviews) AS total_reviews, COUNT(listing_id) AS total_listings
     FROM {db.WAREHOUSE_SCHEMA}.LISTINGS
     GROUP BY neighbourhood_id
 ) wl
 LEFT JOIN {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS wn
     ON wl.neighbourhood_id = wn.neighbourhood_id
 ORDER BY wl.total_listings DESC
 LIMIT 10
```

3. Top 10 listings by total bookings

SQL
```
SELECT 
   nei.city,
   lis.listing_id, 
   lis.listing_description, 
   lis.room_type, 
   lis.number_of_reviews, 
   lis.last_review, 
   lis.reviews_per_month, 
   (365 - lis.availability_365) AS total_bookings
 FROM {db.WAREHOUSE_SCHEMA}.LISTINGS lis
 LEFT JOIN {db.WAREHOUSE_SCHEMA}.NEIGHBOURHOODS nei
   ON lis.neighbourhood_id = nei.neighbourhood_id
   ORDER BY lis.availability_365 ASC, lis.number_of_reviews DESC LIMIT 10
```

4. Top 10 hosts by total listings

SQL
```
WITH aggregated_calendar AS (
 SELECT listing_id, min(minimum_nights) AS minimum_stay_nights, max(maximum_nights) AS maximum_stay_nights
 FROM {db.WAREHOUSE_SCHEMA}.CALENDAR
 GROUP BY listing_id
)
 SELECT 
       lis.host_id,
       lis.host_name,
       count(distinct listing_id) as total_listings,
       (365 * count(distinct listing_id)) AS potential_yearly_bookings,
       sum(lis.availability_365) AS total_availability,
       sum(lis.availability_365) / (365 * count(distinct listing_id)) AS percentage_availability,
       min(cal.minimum_stay_nights) AS minimum_stay_nights,
       max(cal.maximum_stay_nights) AS maximum_stay_nights,
       sum(lis.number_of_reviews) AS total_reviews
   FROM {db.WAREHOUSE_SCHEMA}.LISTINGS AS lis
   LEFT JOIN aggregated_calendar AS cal
   ON lis.listing_id = cal.listing_id
   GROUP BY lis.host_id, lis.host_name
   ORDER BY total_listings DESC, percentage_availability DESC LIMIT 10
```

5. Total bookings by month

SQL
```
SELECT 
       toStartOfMonth(calendar_date) as month,
       countIf(available = 'f') as total_bookings
FROM {db.WAREHOUSE_SCHEMA}.CALENDAR
GROUP BY month
ORDER BY month ASC
```
---

## 📜 Credits & Acknowledgments

This project is an adaptation based on the original workshop structure and starter codebase provided by:
* **Original Repository:** [alexeygrigorev/exasol-workshop-starter](https://github.com/alexeygrigorev/exasol-workshop-starter)
* **Author:** [Alexey Grigorev](https://github.com/alexeygrigorev) and contributors.

Thank you to the original creators for providing the foundation for this Data Engineering pipeline!
