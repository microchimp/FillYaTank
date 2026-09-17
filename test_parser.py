#!/usr/bin/env python3
"""Tests for the buying-tip keyword rules (no network). Run: python3 test_parser.py"""

import main

# Every distinct ACCC wording seen in archived pages, Apr 2025 - Sep 2026
ACCC_WORDINGS = {
    "prices appear to be around the lowest point of the cycle now is a good time for motorists to buy petrol.": "BUY",
    "prices appear to be around the lowest point of the cycle. now is a good time for motorists to buy petrol.": "BUY",
    "prices are increasing if motorists shop around , they may find some retailers who have not yet increased prices.": "WAIT",
    "prices are increasing if motorists shop around, they may find some retailers who have not yet increased prices.": "WAIT",
    "prices are increasing if motorists shop around , they may find some retailers that have not yet increased prices.": "WAIT",
    "prices are increasing. if motorists shop around , they may find some retailers that have not yet increased prices.": "WAIT",
    "prices are decreasing and may decrease further motorists looking to buy petrol can shop around for the lowest prices.": "WAIT",
    "prices are decreasing and may decrease further. motorists looking to buy petrol can shop around for the lowest prices.": "WAIT",
    "while the price cycle is around a high point , we encourage motorists to use fuel price apps and websites to find lower priced retailers.": "WAIT",
    "prices appear to be increasing ; we encourage motorists to use fuel price apps and websites to find lower priced retailers": "WAIT",
    "prices have decreased; we encourage motorists to use fuel price apps and websites to find lower priced retailers.": "WAIT",
    "prices have decreased motorists looking to buy petrol can shop around for the lowest prices.": "WAIT",
    "prices have increased if motorists shop around , they may find some retailers who have not yet increased prices.": "WAIT",
    "prices have increased motorists looking to buy petrol can shop around for the lowest prices.": "WAIT",
    "prices have increased motorists looking to buy petrol can shop around for lower priced retailers.": "WAIT",
}

# Plausible rewordings: confident where safe, UNCLEAR (sent to AI) where not
REWORDINGS = {
    "prices appear to be around the lowest&nbsp;point of the cycle. now is a good time to buy": "BUY",
    "prices have reached the bottom of the price cycle": "BUY",
    "prices are at or near their lowest": "BUY",
    "petrol prices have bottomed out": "BUY",
    "now is a good time for motorists to fill up": "BUY",
    "prices are rising sharply": "WAIT",
    "prices are around the peak of the cycle": "WAIT",
    "prices are falling and may fall further": "WAIT",
    "prices are near the lowest point but may decrease further": "UNCLEAR",
    "prices are not yet at the lowest point": "UNCLEAR",
    "it is not a good time to buy": "UNCLEAR",
    "prices are stable": "UNCLEAR",
    "": "UNCLEAR",
}


def run(cases: dict, label: str) -> int:
    failures = 0
    for text, expected in cases.items():
        got, reason = main.classify_tip(text)
        if got != expected:
            failures += 1
            print(f"FAIL [{label}] expected {expected}, got {got} ({reason}): {text!r}")
    print(f"{label}: {len(cases) - failures}/{len(cases)} passed")
    return failures


def run_extraction_fixture() -> int:
    """The scraper must still find all five tips in a saved copy of the ACCC page."""
    from pathlib import Path
    html = (Path(__file__).parent / "tests" / "fixtures" / "accc_2026-09-17.html").read_text()
    tips = main.extract_buying_tips_v2(html)
    missing = [city for city in main.CITIES if not tips.get(city)]
    unclear = [city for city in main.CITIES if tips.get(city) and main.classify_tip(tips[city])[0] == "UNCLEAR"]
    for city in missing:
        print(f"FAIL [extraction] no tip found for {city}")
    for city in unclear:
        print(f"FAIL [extraction] tip for {city} not recognised: {tips[city]!r}")
    print(f"extraction fixture: {5 - len(missing) - len(unclear)}/5 passed")
    return len(missing) + len(unclear)


if __name__ == "__main__":
    failures = run(ACCC_WORDINGS, "ACCC wordings") + run(REWORDINGS, "rewordings") + run_extraction_fixture()
    raise SystemExit(1 if failures else 0)
