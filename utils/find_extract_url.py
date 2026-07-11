"""Extract metadata from InsideAirbnb URLs.

This module parses InsideAirbnb URLs to extract:
- country, state/province, city, date
- type (data or visualisations)
- filename and full URL
"""

import os
import re
import json
from typing import Dict, Optional
from playwright.sync_api import sync_playwright
import json
import logging
import time


DATASET_URL = "https://insideairbnb.com/get-the-data/"

OUTPUT_FILE_JSON = "data/latest_airbnb_urls_11_06.json"
ALL_OUTPUT_FILE_JSON = "data/airbnb_urls.json"

OUTPUT_FILE_CSV = "data/latest_airbnb_urls.csv"

CHECKPOINT_FILE = "data/latest_scrape_checkpoint.json"
LOG_FILE = "data/latest_scrape_log.txt"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=LOG_FILE, filemode='a')

INSIDE_AIRBNB_URL = re.compile(
    r"^https://data\.insideairbnb\.com/"
    r"(?P<country>[^/]+)"
    r"(?:/(?P<state>[^/]+)(?:/(?P<city>[^/]+))?)?"
    r"/(?P<date>\d{4}-\d{2}-\d{2})/"
    r"(?P<type>[^/]+)/(?P<name>[^/]+)$"
)

'''
checkpoint file structure:
{
  "buttons_clicked": 5,
  "total_buttons": 10,
  "extracted_urls": [...] # includes all URLs extracted so far, to avoid duplicates on resume
}
'''
def load_checkpoint():
    """Load progress from previous run if it exists"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                checkpoint = json.load(f)
                logging.info(f"Resuming from previous run.")
                logging.info(f"  - Buttons clicked: {checkpoint['buttons_clicked']}/{checkpoint['total_buttons']}")
                logging.info(f"  - URLs processed: {len(checkpoint['extracted_urls'])}")
                return checkpoint
        except Exception as e:
            logging.info(f"Could not load checkpoint: {e}. Starting fresh.")
    return {"buttons_clicked": 0, "total_buttons": 0, "extracted_urls": []}

def save_checkpoint(buttons_clicked, total_buttons, urls):
    """Save current progress to checkpoint file"""
    with open(CHECKPOINT_FILE, "a") as f:
        json.dump({
            "timestamp": time.time(),
            "buttons_clicked": buttons_clicked,
            "total_buttons": total_buttons,
            "extracted_urls": urls
        }, f, indent=2)

def extract_url_metadata(url: str) -> Optional[Dict[str, str]]:
    """Extract metadata from an InsideAirbnb URL.
    
    Args:
        url: Full URL from InsideAirbnb dataset
        
    Returns:
        Dictionary with extracted metadata or None if URL doesn't match pattern
    """
    # Pattern: https://data.insideairbnb.com/{country}/{state}/{city}/{date}/{type}/{filename}
    match = INSIDE_AIRBNB_URL.match(url)
    if not match:
        logging.info(f"URL does not match expected patterns: {url}")
        return None

    return {
        "country": match.group("country"),
        "state": match.group("state"),
        "city": match.group("city"),
        "date": match.group("date"),
        "type": match.group("type"),
        "name": match.group("name"),
        "url": url,
    }

def run_playwright():
    # Load checkpoint from previous run
    # checkpoint = load_checkpoint()
    # buttons_clicked = checkpoint["buttons_clicked"]
    # extracted_urls = checkpoint["extracted_urls"]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)  # Set headless=True if you don't want to see the browser
        page = browser.new_page()
        page.set_default_timeout(60000)  # Set a longer timeout to avoid issues with slow loading 60000 ms = 1 minute = 60 seconds
        
        print("Loading Inside Airbnb...")
        page.goto(DATASET_URL)
        
        # 1. Find all the "show archived data" buttons on the page
        # Using the exact text match to find them
        # archive_buttons = page.locator(".showArchivedData")
        # archive_buttons = page.get_by_text("show", exact=True).all()
        
        # count = len(archive_buttons)
        # print(f"Found {count} archive buttons. Clicking them all now...")
        
        # if buttons_clicked > 0:
        #     print(f"Resuming: {buttons_clicked} buttons already clicked, continuing from button {buttons_clicked + 1}...")
        
        # # 2. Loop through and click every single one to reveal the data
        # for i in range(buttons_clicked, 5):  # Limit to first 5 buttons for TESTING, change to count for FULL RUN
        #     try:
        #         archive_buttons[i].scroll_into_view_if_needed(timeout=5000)  # Scroll to the button if it's not visible
        #         archive_buttons[i].wait_for(timeout=0)  # Wait until the button is visible
        #         archive_buttons[i].click()  # Click the button with a timeout
        #         time.sleep(5) # Wait a bit for the content to load after clicking
        #         buttons_clicked = i + 1
        #         # Save checkpoint after each button click
        #         save_checkpoint(buttons_clicked, count, metadata_list)
        #     except Exception as e:
        #         print(f"Warning: Could not click button {i+1}/{count}. Error: {e}")
        #         # Save checkpoint before exiting on error
        #         save_checkpoint(buttons_clicked, count, metadata_list)
        #         break  # Exit the loop if we can't click a button, to avoid infinite errors

        # print("All sections expanded! Extracting links...")
        
        # 3. Grab all the links that end in .csv or .csv.gz or .geojson (these are the dataset files we want)
        # Playwright lets us search the updated HTML directly
        page.wait_for_load_state()
        # links = page.locator("a[href*='.csv'], a[href*='.csv.gz'], a[href*='.geojson']").all()
        links = page.get_by_role("link").filter(has_text=re.compile(r"\.(csv|csv\.gz|geojson)$", re.IGNORECASE)).all()
        print(f"Found {len(links)} links to CSV/CSV.GZ/GeoJSON files. Extracting metadata from each URL now...")

        # 4. Extract URL and store it in a list
        urls_list = []
        for i, link in enumerate(links):
            try:
                url = link.get_attribute("href")
                urls_list.append(url)
                if i < 20:
                    print(f"Getting URL {i+1}: {url}")              
            except Exception as e:
                logging.addLevelName(logging.ERROR, f"Error processing URL {i}: {e}")
        browser.close()
    return urls_list
    
    # 5. Clear checkpoint after successful completion
    # if os.path.exists(CHECKPOINT_FILE):
    #     os.remove(CHECKPOINT_FILE)
    #     print("Scraping completed successfully! Checkpoint cleared.")

if __name__ == "__main__":
    urls_list = run_playwright()
    metadata_list = []
    checkpoint = load_checkpoint()
    extracted_urls = checkpoint["extracted_urls"]

    for i, url in enumerate(urls_list):
        try:
            url_metadata = extract_url_metadata(url)
            if url_metadata is not None:
                metadata_list.append(url_metadata)
                extracted_urls.append(url)  # Add to list of extracted URLs for checkpointing    
            else:
                logging.warning(f"Warning: Metadata extraction failed for URL {i+1}/{len(urls_list)}: {url}")                 
        except Exception as e:
            logging.addLevelName(logging.ERROR, f"Error processing URL {i}: {e}")
            
    save_checkpoint(0,0,extracted_urls) # Save checkpoint for URLs processed
    

    # 5. Save to JSON file
    with open(OUTPUT_FILE_JSON, "w") as f:
        json.dump(metadata_list, f, indent=2)
    
    # 6. Clear checkpoint after successful completion
    # if os.path.exists(CHECKPOINT_FILE):
    #     os.remove(CHECKPOINT_FILE)
    #     print("Scraping completed successfully! Checkpoint cleared.")


'''
# something to consider for future improvement: instead of saving checkpoint after every single URL processed, we could save it after every N URLs (e.g. every 10 or 20) to reduce the number of writes to disk, which can be slow. We would just need to make sure to save the final checkpoint at the end of the run as well, to capture any remaining progress.

# 1. example of data extraction
URL_LIST = [
        "https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2026-01-16/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-12-11/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-11-07/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-10-05/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-09-06/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-08-04/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-07-04/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/ny/albany/2025-06-09/data/listings.csv.gz",
        "https://data.insideairbnb.com/the-netherlands/north-holland/amsterdam/2025-09-11/data/listings.csv.gz",
        "https://data.insideairbnb.com/the-netherlands/north-holland/amsterdam/2025-06-09/data/listings.csv.gz",
        "https://data.insideairbnb.com/belgium/vlg/antwerp/2025-09-28/data/listings.csv.gz",
        "https://data.insideairbnb.com/belgium/vlg/antwerp/2025-06-25/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/nc/asheville/2025-09-22/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/nc/asheville/2025-06-17/data/listings.csv.gz",
        "https://data.insideairbnb.com/united-states/nc/asheville/2025-06-17/data/listings.csv.gz",
        "https://www.data.gov.uk/dataset/176ae264-2484-4afe-a297-d51798eb8228/prescribing-by-gp-practice-presentation-level",
        "https://www.data.gov.uk/dataset/176ae264-2484-4afe-a297-d51798eb8228/prescribing-by-gp-practice-presentation-level"
    ]
    for url in URL_LIST:
        metadata = extract_url_metadata(url)
        print(metadata)

# 2. writing to JSON file
 # ensure output directory exists, then write JSON file with indentation
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print("\nSaved metadata for {} locations to {}".format(len(location_list), OUTPUT_FILE))

# 3. sample url
https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2026-01-16/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-12-11/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-11-07/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-10-05/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-09-06/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-08-04/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-07-04/data/listings.csv.gz
https://data.insideairbnb.com/united-states/ny/albany/2025-06-09/data/listings.csv.gz
https://data.insideairbnb.com/the-netherlands/north-holland/amsterdam/2025-09-11/data/listings.csv.gz
https://data.insideairbnb.com/the-netherlands/north-holland/amsterdam/2025-06-09/data/listings.csv.gz
https://data.insideairbnb.com/belgium/vlg/antwerp/2025-09-28/data/listings.csv.gz
https://data.insideairbnb.com/belgium/vlg/antwerp/2025-06-25/data/listings.csv.gz
https://data.insideairbnb.com/united-states/nc/asheville/2025-09-22/data/listings.csv.gz
https://data.insideairbnb.com/united-states/nc/asheville/2025-06-17/data/listings.csv.gz
https://data.insideairbnb.com/united-states/nc/asheville/2025-06-17/data/listings.csv.gz
https://www.data.gov.uk/dataset/176ae264-2484-4afe-a297-d51798eb8228/prescribing-by-gp-practice-presentation-level
https://www.data.gov.uk/dataset/176ae264-2484-4afe-a297-d51798eb8228/prescribing-by-gp-practice-presentation-level

# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/data/listings.csv.gz
# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/data/calendar.csv.gz
# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/data/reviews.csv.gz
# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/visualisations/listings.csv
# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/visualisations/reviews.csv
# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/visualisations/neighbourhoods.csv
# https://data.insideairbnb.com/united-states/ny/albany/2026-02-15/visualisations/neighbourhoods.geojson
 
# 4. building location index
def build_location_index(metadata_items):
    """Group extracted URLs by location and date.

    The output structure is:
    {
        (country, state, city): {
            "country": ...,
            "state": ...,
            "city": ...,
            "snapshots": [
                {
                    "date": date,
                    "period": yyyymm,
                    "data": {name: url},
                    "visualizations": {name: url},
                }
            ]
        }
    }
    """
    locations = {}

    for item in metadata_items:
        # Use a tuple of (country, state, city) as the key for grouping
        key = (item["country"], item["state"], item["city"])

        # The setdefault(key, value) method returns the value of the item with the specified key.
        # If the key does not exist, insert the key, with the specified value
        location = locations.setdefault(
            key,
            {
                "country": item["country"],
                "state": item["state"],
                "city": item["city"],
                "periods": {},
            }
        )

        snapshot = location["periods"].setdefault(
            item["date"],
            {
                "date": item["date"],
                "period": item["date"].replace("-", "")[:6],
                "data": {},
                "visualizations": {},
            },
        )

        snapshot_type = "data" if item["type"] == "data" else "visualizations"
        snapshot[snapshot_type][item["name"]] = item["url"]

    return locations
'''

