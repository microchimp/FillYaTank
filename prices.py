#!/usr/bin/env python3
"""
Build data/prices.json: daily average regular unleaded price for each
city over the last few weeks, for the price charts on the website.

Sources (added per city as access becomes available):
- Perth: FuelWatch historic prices, Government of Western Australia
  (CC BY 4.0). Monthly CSVs are updated each day with the previous
  day's prices.
"""

import csv
import io
import json
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

DATA_FILE = Path(__file__).parent / "data" / "prices.json"
DAYS = 45

FUELWATCH_CSV = "https://warsydprdstafuelwatch.blob.core.windows.net/historical-reports/FuelWatchRetail-{month:02d}-{year}.csv"


def months_covering(start: date, end: date) -> list[tuple[int, int]]:
    """(year, month) pairs from start to end inclusive."""
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def perth_daily_averages(start: date, end: date) -> list[list]:
    """Average Perth metro ULP price per day from FuelWatch monthly CSVs."""
    by_day: dict[date, list[float]] = {}
    for year, month in months_covering(start, end):
        response = requests.get(FUELWATCH_CSV.format(year=year, month=month), timeout=120)
        if response.status_code == 404:
            continue  # month not published yet
        response.raise_for_status()
        rows = csv.DictReader(io.StringIO(response.content.decode("utf-8", errors="ignore")))
        for row in rows:
            if row.get("PRODUCT_DESCRIPTION") != "ULP" or row.get("REGION_DESCRIPTION") != "Metro":
                continue
            day = datetime.strptime(row["PUBLISH_DATE"], "%d/%m/%Y").date()
            if start <= day <= end:
                by_day.setdefault(day, []).append(float(row["PRODUCT_PRICE"]))
    return [[day.isoformat(), round(statistics.mean(prices), 1)] for day, prices in sorted(by_day.items())]


SOURCES = {
    "perth": {
        "build": perth_daily_averages,
        "source": "FuelWatch, Government of Western Australia (CC BY 4.0)",
    },
}


def main() -> int:
    end = date.today()
    start = end - timedelta(days=DAYS + 3)

    existing = {}
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text()).get("cities", {})

    cities = {}
    for city, config in SOURCES.items():
        try:
            days = config["build"](start, end)[-DAYS:]
            if not days:
                raise ValueError("no data returned")
            cities[city] = {"source": config["source"], "days": days}
            print(f"{city}: {len(days)} days, latest {days[-1][0]} = {days[-1][1]} c/L")
        except Exception as e:
            # Keep the last good data rather than blanking the chart
            print(f"Warning: {city} update failed ({e}); keeping previous data")
            if city in existing:
                cities[city] = existing[city]

    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps({"fuel": "Regular unleaded (ULP)", "unit": "cents per litre", "cities": cities}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
