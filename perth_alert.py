#!/usr/bin/env python3
"""
Perth "prices jump tomorrow" alert.

FuelWatch (Government of WA) publishes every station's price for the next
day by 2:30pm WST, and those prices are locked in for 24 hours. This runs
each afternoon, compares tomorrow's Perth metro unleaded prices with today's
at the same stations, and emails Perth subscribers when prices are about to
jump, so they can fill up today.

Env: RESEND_API_KEY, FROM_EMAIL, SITE_URL, SECRET_KEY, ADMIN_TOKEN, TEST_EMAIL
     SIMULATE_PERTH_JUMP=true  force an alert to TEST_EMAIL only, write nothing
"""

import json
import os
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import main

RSS_URL = "https://www.fuelwatch.wa.gov.au/fuelwatch/fuelWatchRSS"
USER_AGENT = "FillYaTank/1.0 (+https://fillyatank.app)"
JUMP_THRESHOLD = 5.0  # cents per litre, average across matched stations
MIN_STATIONS = 100

DATA_DIR = Path(__file__).parent / "data"
LAST_RUN_FILE = DATA_DIR / "perth_last_run.txt"
ALERT_STATE_FILE = DATA_DIR / "perth_alert.json"

SIMULATE = os.environ.get("SIMULATE_PERTH_JUMP", "").lower() == "true"


def fetch_prices(day: str) -> tuple[str | None, dict[tuple[str, str], float]]:
    """Metro unleaded prices for 'today' or 'tomorrow', keyed by station."""
    response = requests.get(
        RSS_URL,
        params={"Product": 1, "Day": day},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()
    items = ET.fromstring(response.content).findall(".//item")
    prices = {}
    date = None
    for item in items:
        price = item.findtext("price")
        if not price:
            continue
        date = date or item.findtext("date")
        prices[(item.findtext("trading-name") or "", item.findtext("address") or "")] = float(price)
    return date, prices


def load_alert_state() -> dict:
    if ALERT_STATE_FILE.exists():
        return json.loads(ALERT_STATE_FILE.read_text())
    return {}


def run() -> int:
    perth_today = datetime.now(ZoneInfo("Australia/Perth")).date()
    print(f"FillYaTank Perth check - {datetime.now(ZoneInfo('Australia/Perth')).isoformat()}")

    today_date, today = fetch_prices("today")
    tomorrow_date, tomorrow = fetch_prices("tomorrow")
    common = set(today) & set(tomorrow)
    print(f"Today {today_date}: {len(today)} stations · Tomorrow {tomorrow_date}: {len(tomorrow)} stations · matched {len(common)}")

    if not tomorrow or tomorrow_date == today_date or len(common) < MIN_STATIONS:
        print("Tomorrow's prices aren't published yet (or too few stations to compare). Nothing to do.")
        return 1

    today_avg = statistics.mean(today[k] for k in common)
    tomorrow_avg = statistics.mean(tomorrow[k] for k in common)
    change = tomorrow_avg - today_avg
    rising = sum(1 for k in common if tomorrow[k] > today[k])
    print(f"Average today {today_avg:.1f} c/L, tomorrow {tomorrow_avg:.1f} c/L, change {change:+.1f} c/L ({rising} of {len(common)} stations rising)")

    if SIMULATE:
        change = max(change, 15.0)
        print("TEST MODE: forcing a jump and emailing TEST_EMAIL only")

    state = load_alert_state()
    already_sent = state.get("last_alert_for") == tomorrow_date

    if change >= JUMP_THRESHOLD and (SIMULATE or not already_sent):
        recipients = main.load_subscribers().get("perth", [])
        if SIMULATE:
            recipients = [main.TEST_EMAIL] if main.TEST_EMAIL else []
        print(f"Jump of {change:.1f} c/L: alerting {len(recipients)} Perth subscriber(s)")

        failures = 0
        for email in recipients:
            ok = main.send_alert(
                email, "perth",
                subject=f"⛽ Perth petrol jumps about {round(change)}c tomorrow. Fill up today",
                headline=f"Perth prices jump about {round(change)} cents a litre tomorrow, so today is the bottom of the cycle.",
                details=[
                    f"Average unleaded today: {today_avg:.1f}¢/L. Tomorrow: {tomorrow_avg:.1f}¢/L.",
                    f"On a 55 litre tank that's about ${change * 55 / 100:.0f} saved by filling up today.",
                    "Source: FuelWatch next-day prices, which WA stations must lock in for 24 hours from 6am.",
                ],
            )
            failures += 0 if ok else 1

        if not SIMULATE:
            state["last_alert_for"] = tomorrow_date
            ALERT_STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
        if failures:
            print(f"✗ {failures} alert(s) failed to send")
            return 1
    elif already_sent:
        print("Already alerted for this jump.")
    else:
        print("No jump tomorrow. No alerts sent.")

    if not SIMULATE:
        LAST_RUN_FILE.write_text(perth_today.isoformat() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
