"""
Detect CSV format for Inside Airbnb data files.

Downloads the first 4KB = 4096 bytes of a CSV file using an HTTP Range request
and determines the row separator (CRLF or LF), number of columns,
and whether the file has a header row.
"""

from dataclasses import dataclass

import requests
import gzip

HEADER_NAMES = ["id", "name", "host_id", "host_name", "neighbourhood_group", "neighbourhood", "latitude", "longitude", "room_type", "price", "minimum_nights", "number_of_reviews_ltm", "last_review", "number_of_reviews", "calculated_host_listings_count", "availability_365", "license"]


@dataclass
class CsvFormat:
    row_separator: str
    num_columns: int
    has_header: bool
    skip: int

# sample_size can be in bytes (for .CSV files) or in rows (for .CSV.GZ files)
def download_sample(url: str, sample_size: int = 4096) -> bytes:
    # request.get parameters:
    # - headers: set Range to download only the first sample_size bytes
    # - timeout: set a timeout to avoid hanging on slow or unresponsive servers - 30 seconds should be sufficient for a small sample
    if url.endswith(".csv"):
        response = requests.get(url, headers={"Range": f"bytes=0-{sample_size}"}, timeout=30)
        sample = response.content
    elif url.endswith(".csv.gz"):
        response = requests.get(url, stream=True, timeout=30)
        sample = b""
        with gzip.GzipFile(fileobj=response.raw) as gz_file:
            for i, line in enumerate(gz_file):
                if i > sample_size:
                    break
                sample += line
    else:
        raise ValueError(f"Unsupported file format for URL: {url}")
        
    response.raise_for_status()
    return sample


def detect_row_separator(sample: bytes) -> str:
    if b"\r\n" in sample:
        return "CRLF"
    else:
        return "LF"


def count_columns(lines: list[bytes]) -> int:
    first_line = lines[0].decode("utf-8", errors="ignore")
    num_columns = len(first_line.split(","))

    if len(lines) >= 2 and lines[1].strip():
        second_line = lines[1].decode("utf-8", errors="ignore")
        data_cols = len(second_line.split(","))
        if data_cols != num_columns:
            num_columns = data_cols

    return num_columns


def check_has_header(line: str) -> bool:
    lower_line = line.lower()
    for name in HEADER_NAMES:
        if name in lower_line:
            return True
    return False


def detect_csv_format(url: str, sample_size: int = 4096) -> CsvFormat:
    if url.endswith(".csv"):
        sample = download_sample(url, sample_size)
    elif url.endswith(".csv.gz"):
        sample = download_sample(url, sample_size = 50)

    lines = sample.split(b"\n")
    first_line = lines[0].decode("utf-8", errors="ignore")

    row_separator = detect_row_separator(sample)
    num_columns = count_columns(lines)
    has_header = check_has_header(first_line)

    if has_header:
        skip = 1
    else:
        skip = 0

    return CsvFormat(
        row_separator=row_separator,
        num_columns=num_columns,
        has_header=has_header,
        skip=skip,
    )