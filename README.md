# Workshop : Building data pipeline with Python, SQL
This repository contains a data pipeline (ETL pipeline) designed to ingest, clean, and store the [Inside Airbnb dataset](https://insideairbnb.com/get-the-data/) into a data warehouse. The system implements a Star Schema data model.

## Data pipeline architecture
Each CSV file is ingested directly from the source URL and moves through a multi-stage staging pipeline to ensure data integrity, cleanliness, and transformation before being loaded into the production analytics layer:

https://data.insideairbnb.com/united-states/ny/albany/2026-06-16/data/calendar.csv.gz 
       │
       V
 1. STG_RAW_xxxx       ──> Raw data ingestion directly from URL into temporary staging tables.
       │
       V
 2. STG_xxxx           ──> Data enrichment and basic cleaning
       │
       V
 3. Warehouse (Final)  ──> Idempotent insert into production Fact/Dimension tables.

## Data model design (star schema)
Once the data is processed, it is organized into a star schema optimized for fast analytical queries:

### 1. Fact table

CALENDAR: Stores detailed transaction booking records for 365 days in the future (listing_id, calendar_date, available, minimum_nights, maximum_nights, period).

### 2. Dimension tables

NEIGHBOURHOODS: Contains neighbourhoods details including which country, state, and city they are in.

LISTINGS: A lookup directory for the active listings that are currently for rent

## ETL step-by-step implementation
Step 1: Raw data ingestion from URL
We initialize raw staging tables to pull data streams directly from the source CSV URLs. The source files may use CRLF (\r\n) line endings and feature a trailing comma at the end of each line.
