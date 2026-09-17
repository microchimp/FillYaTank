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


if __name__ == "__main__":
    failures = run(ACCC_WORDINGS, "ACCC wordings") + run(REWORDINGS, "rewordings")
    raise SystemExit(1 if failures else 0)
