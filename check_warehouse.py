"""
Run analytics queries to verify the data warehouse is working.

Usage:
    uv run python code/test/check_warehouse.py
"""

import utils.db as db

def main() -> None:
    conn = db.connect()
    db.ensure_schemas(conn)

    print("=== Row counts ===")
    rows = conn.query(f"""
        SELECT 
            name AS TABLE_NAME, 
            total_rows AS TABLE_ROW_COUNT
        FROM system.tables
        WHERE database = '{db.WAREHOUSE_SCHEMA}'
        AND name IN ('NEIGHBOURHOODS', 'LISTINGS', 'CALENDAR')
    """)
    
    counts = {table_name: int(row_count or 0) for table_name, row_count in rows.result_rows}
    for table in ["NEIGHBOURHOODS", "LISTINGS", "CALENDAR"]:
        count = counts.get(table, 0)
        print(f"  {table}: {count:,} rows")

    print()
    print("=== Top 10 neighbourhoods by total listings ===")
    rows = conn.query(f"""
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
    """)

    print(f" {'COUNTRY':<10} {'STATE':<10} {'CITY':<20} {'NEIGHBOURHOOD_GROUP':<16} {'NEIGHBOURHOOD NAME':<40} {'REVIEWS':>10} {'LISTINGS':>12}")
    print(f"  {'-'*10} {'-'*10} {'-'*20} {'-'*16} {'-'*40} {'-'*10} {'-'*12}")
    
    for row in rows.result_rows:
        print(f"  {row[0]:<10} {row[1]:<10} {row[2]:<20} {row[3]:<16} {(row[4] or 'N/A'):<40} {int(row[5]):>10,} {float(row[6]):>12,.2f}")

    print()
    print("=== Check booking volume with availability ===")
    rows = conn.query(f"""
        SELECT SUM(cal.total_bookings) as total_bookings, 
                        SUM(lis.availability_365) AS total_availability, 
                        (total_bookings + total_availability)/count(lis.listing_id) as check_max_availability_per_listing 
        FROM (
            SELECT listing_id, countIf(available = 'f') as total_bookings
            FROM {db.WAREHOUSE_SCHEMA}.CALENDAR
            GROUP BY listing_id) AS cal
            LEFT JOIN {db.WAREHOUSE_SCHEMA}.LISTINGS lis
            ON cal.listing_id = lis.listing_id
    """)
    for row_dict in rows.named_results():
        print(row_dict)

    print()
    print("=== Top 10 listings by total bookings ===")
    rows = conn.query(f"""SELECT 
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
                        ORDER BY lis.availability_365 ASC, lis.number_of_reviews DESC LIMIT 10""")
    
    print(f"  {'CITY':<20} {'LISTING':<20} {'LISTING NAME':<50} {'ROOM TYPE':<15} {'REVIEWS':>10} {'LAST REVIEW':<12} {'REVIEWS/MONTH':<15} {'BOOKINGS':>12}")
    print(f"  {'-'*20} {'-'*20} {'-'*50} {'-'*15} {'-'*10} {'-'*12} {'-'*15} {'-'*12}")
    for row in rows.result_rows:
        date_str = row[5].strftime('%Y-%m-%d') if row[5] else 'N/A'
        print(f"  {row[0]:<20} {(row[1] or 'N/A'):<20} {(row[2] or 'N/A'):<50} {(row[3] or 'N/A'):<15} {int(row[4]):>10,} {date_str:<12} {float(row[6] or 0):<15.2f} {int(row[7]):>12,}")

    print()
    print("=== Check listings volume for each host with calculated_host_listings ===")
    rows = conn.query(f"""
                      SELECT host_id, total_listings, calculated_host_listings
                      FROM (
                        SELECT host_id, count(distinct listing_id) as total_listings, avg(calculated_host_listings_count) as calculated_host_listings
                        FROM {db.WAREHOUSE_SCHEMA}.LISTINGS
                        GROUP BY host_id) host_listings
                      WHERE total_listings > calculated_host_listings
                      ORDER BY total_listings DESC
                      """)
    
    print(f"  {'HOST ID':<20} {'TOTAL LISTINGS':<20} {'CALCULATED HOST LISTINGS':<50}")
    print(f"  {'-'*20} {'-'*20} {'-'*50}")
    for row_dict in rows.named_results():
        print(row_dict)

    print()
    print("=== Top 10 hosts by total listings ===")
    rows = conn.query(f"""WITH aggregated_calendar AS (
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
                        """)

    print(f"  {'HOSTS':<20} {'NAME':<20} {'LISTINGS':<15} {'BOOKINGS':<15} {'AVAILABILITY':<15} {'PERCENTAGE AVAIL':<15} {'MIN STAY NIGHTS':<15} {'MAX STAY NIGHTS':<15} {'REVIEWS':<15}")
    print(f"  {'-'*20} {'-'*20} {'-'*15} {'-'*15} {'-'*15} {'-'*15} {'-'*15} {'-'*15} {'-'*15}")
    for row in rows.result_rows:
        print(f"  {row[0]:<20} {(row[1].encode('ascii', errors='ignore').decode('ascii') or 'N/A'):<20} {int(row[2]):<15} {int(row[3]):<15} {int(row[4] or 0):<15.2f} {float(row[5] * 100 or 0) :<15.2f} {int(row[6] or 0):<15} {int(row[7] or 0):<15} {int(row[8] or 0):<15}")

    print()
    print("=== Total bookings by month ===")
    rows = conn.query(f"""SELECT 
                            toStartOfMonth(calendar_date) as month,
                            countIf(available = 'f') as total_bookings
                        FROM {db.WAREHOUSE_SCHEMA}.CALENDAR
                        GROUP BY month
                        ORDER BY month ASC
                        """)

    print(f"  {'MONTH':<20} {'TOTAL BOOKINGS':<20}")
    print(f"  {'-'*20} {'-'*20}")
    for row in rows.result_rows:
        date_str = row[0].strftime('%Y-%m-%d') if row[0] else 'N/A'
        print(f"  {date_str:<20} {int(row[1]):<20}")

    conn.close()

    
if __name__ == "__main__":
    main()