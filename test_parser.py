#!/usr/bin/env python3
"""Test the parsing logic with sample ACCC HTML"""

import re

# Sample buying tips text extracted from the actual ACCC page
SAMPLE_TIPS = {
    "sydney": "prices appear to be around the lowest point of the cycle now is a good time for motorists to buy petrol",
    "melbourne": "while the price cycle is around a high point we encourage motorists to use fuel price apps and websites to find lower priced retailers",
    "brisbane": "while the price cycle is around a high point we encourage motorists to use fuel price apps and websites to find lower priced retailers",
    "adelaide": "prices appear to be around the lowest point of the cycle now is a good time for motorists to buy petrol",
    "perth": "prices are decreasing and may decrease further motorists looking to buy petrol can shop around for the lowest prices"
}

def classify_phase(tip_text: str) -> str:
    """
    Classify the buying tip into BUY or WAIT phase.
    """
    text = tip_text.lower()
    
    # WAIT signals take priority - check these first
    wait_phrases = [
        "decreasing",
        "may decrease",
        "shop around",
        "high point",
        "increasing",
        "around a high"
    ]
    
    if any(phrase in text for phrase in wait_phrases):
        return "WAIT"
    
    # BUY signals - prices at the bottom
    buy_phrases = [
        "lowest point",
        "good time to buy",
        "now is a good time",
        "around the lowest",
        "at the lowest"
    ]
    
    if any(phrase in text for phrase in buy_phrases):
        return "BUY"
    
    return "WAIT"


def test_classification():
    print("Testing classification logic with sample ACCC data:")
    print("=" * 50)
    
    for city, tip in SAMPLE_TIPS.items():
        phase = classify_phase(tip)
        print(f"{city.capitalize():12} → {phase:4}  |  \"{tip[:50]}...\"")
    
    print()
    print("Expected results:")
    print("  Sydney    → BUY  (lowest point)")
    print("  Melbourne → WAIT (high point)")
    print("  Brisbane  → WAIT (high point)")
    print("  Adelaide  → BUY  (lowest point)")
    print("  Perth     → WAIT (decreasing)")


def test_extraction_regex():
    """Test the regex extraction pattern"""
    
    # Simulated HTML snippet
    html_snippet = """
    <h2>Petrol prices in Sydney</h2>
    <p><strong>Buying tip</strong> (updated on Friday):</p>
    <ul>
    <li>prices appear to be around the <strong>lowest</strong> point of the cycle</li>
    <li>now is a good time for motorists to <strong>buy</strong> petrol.</li>
    </ul>
    <p>This chart shows daily average regular unleaded petrol prices in Sydney over the past 45 days.</p>
    """
    
    # Pattern to extract buying tip
    pattern = r"Petrol prices in Sydney.*?Buying tip.*?:(.*?)(?:This chart|Source:|$)"
    match = re.search(pattern, html_snippet, re.IGNORECASE | re.DOTALL)
    
    if match:
        tip_text = match.group(1)
        # Clean HTML
        tip_text = re.sub(r"<[^>]+>", " ", tip_text)
        tip_text = re.sub(r"\s+", " ", tip_text).strip()
        print(f"\nExtracted tip: \"{tip_text}\"")
        print(f"Classification: {classify_phase(tip_text)}")
    else:
        print("Pattern didn't match")


if __name__ == "__main__":
    test_classification()
    test_extraction_regex()
