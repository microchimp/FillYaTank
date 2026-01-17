#!/usr/bin/env python3
"""
Fuel Price Alert System
Scrapes ACCC petrol price cycles page and sends email alerts
when prices hit the bottom of the cycle.

Inspired by "How They Get You" by Chris Kohler
"""

import json
import os
import re
import hashlib
import base64
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Configuration
ACCC_URL = "https://www.accc.gov.au/consumers/petrol-and-fuel/petrol-price-cycles-in-the-5-largest-cities"
CITIES = ["sydney", "melbourne", "brisbane", "adelaide", "perth"]
DATA_DIR = Path(__file__).parent / "data"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alerts@yourdomain.com")
SITE_URL = os.environ.get("SITE_URL", "https://yourusername.github.io/fuel-alert")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")


def fetch_accc_page() -> str:
    """Fetch the ACCC petrol price cycles page."""
    headers = {
        "User-Agent": "FuelPriceAlert/1.0 (Consumer savings tool)"
    }
    response = requests.get(ACCC_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def extract_buying_tips(html: str) -> dict[str, str]:
    """Extract the buying tip text for each city."""
    soup = BeautifulSoup(html, "html.parser")
    tips = {}
    
    for city in CITIES:
        # Find the heading for each city section
        # Format: "Petrol prices in Sydney", "Petrol prices in Melbourne", etc.
        heading_pattern = re.compile(f"Petrol prices in {city.capitalize()}", re.IGNORECASE)
        heading = soup.find(["h2", "h3"], string=heading_pattern)
        
        if not heading:
            print(f"Warning: Could not find section for {city}")
            continue
        
        # Find the buying tip - it's in a paragraph or list after "Buying tip"
        section = heading.find_parent(["section", "div"]) or heading.parent
        
        # Look for the buying tip text
        tip_text = ""
        current = heading.find_next_sibling()
        
        while current and not current.name in ["h2", "h3"]:
            text = current.get_text(strip=True)
            if "buying tip" in text.lower() or "prices" in text.lower():
                # Clean up the text
                tip_text = text
                break
            current = current.find_next_sibling()
        
        # Alternative: search for strong tags with key phrases
        if not tip_text:
            for strong in soup.find_all("strong"):
                strong_text = strong.get_text(strip=True).lower()
                if city in str(strong.find_previous(["h2", "h3"])).lower():
                    parent_text = strong.parent.get_text(strip=True) if strong.parent else ""
                    if parent_text:
                        tip_text = parent_text
                        break
        
        tips[city] = tip_text
    
    return tips


def extract_buying_tips_v2(html: str) -> dict[str, str]:
    """
    Alternative extraction method using regex patterns.
    More robust to HTML structure changes.
    """
    tips = {}
    
    # Pattern to find buying tip sections
    for city in CITIES:
        # Look for the buying tip after each city heading
        pattern = rf"Petrol prices in {city.capitalize()}.*?Buying tip.*?:(.*?)(?:This chart|Source:|$)"
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        
        if match:
            # Clean up the extracted text
            tip_text = match.group(1)
            tip_text = re.sub(r"<[^>]+>", " ", tip_text)  # Remove HTML tags
            tip_text = re.sub(r"\s+", " ", tip_text)  # Normalize whitespace
            tip_text = tip_text.strip()
            tips[city] = tip_text
        else:
            tips[city] = ""
    
    return tips


def classify_phase(tip_text: str) -> str:
    """
    Classify the buying tip into BUY or WAIT phase.
    
    BUY: Prices at lowest point, good time to buy
    WAIT: Prices decreasing, increasing, or at high point
    """
    text = tip_text.lower()
    
    # WAIT signals take priority - check these first
    # - "decreasing" / "may decrease further" = still falling, wait
    # - "high point" / "increasing" = not time to buy
    # - "shop around" = prices variable, not at bottom yet
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
    
    # Default to WAIT if unclear
    return "WAIT"


def load_state() -> dict:
    """Load the previous state from file."""
    state_file = DATA_DIR / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {city: "UNKNOWN" for city in CITIES}


def save_state(state: dict) -> None:
    """Save the current state to file."""
    DATA_DIR.mkdir(exist_ok=True)
    state_file = DATA_DIR / "state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def load_subscribers() -> dict[str, list[str]]:
    """Load subscribers grouped by city."""
    subs_file = DATA_DIR / "subscribers.json"
    if subs_file.exists():
        with open(subs_file) as f:
            return json.load(f)
    return {city: [] for city in CITIES}


def generate_token(email: str, city: str, action: str = "unsubscribe") -> str:
    """Generate a secure token for email actions."""
    data = f"{email}|{city}|{action}|{SECRET_KEY}"
    hash_bytes = hashlib.sha256(data.encode()).digest()[:16]
    return base64.urlsafe_b64encode(hash_bytes).decode().rstrip("=")


def verify_token(email: str, city: str, token: str, action: str = "unsubscribe") -> bool:
    """Verify a token is valid."""
    expected = generate_token(email, city, action)
    return token == expected


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via Resend API."""
    if not RESEND_API_KEY:
        print(f"[DRY RUN] Would send to {to_email}: {subject}")
        return True
    
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_body
        },
        timeout=30
    )
    
    if response.status_code == 200:
        print(f"✓ Sent to {to_email}")
        return True
    else:
        print(f"✗ Failed to send to {to_email}: {response.text}")
        return False


def send_buy_alert(email: str, city: str, tip_text: str) -> bool:
    """Send the BUY alert email."""
    city_display = city.capitalize()
    unsubscribe_token = generate_token(email, city)
    unsubscribe_url = f"{SITE_URL}/unsubscribe.html?email={email}&city={city}&token={unsubscribe_token}"
    
    subject = f"⛽ {city_display} petrol prices are at the bottom"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
    <p style="font-size: 18px; line-height: 1.6; margin: 0 0 24px 0;">
        Prices have hit the low point of the cycle.
    </p>
    
    <p style="font-size: 24px; font-weight: 600; margin: 0 0 24px 0; color: #16a34a;">
        Fill up within 24 hours.
    </p>
    
    <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 32px 0;">
    
    <p style="font-size: 13px; color: #666; margin: 0 0 8px 0;">
        <a href="{unsubscribe_url}" style="color: #666;">Unsubscribe</a>
    </p>
    
    <p style="font-size: 13px; color: #999; margin: 0; font-style: italic;">
        Inspired by "How They Get You" by Chris Kohler
    </p>
</body>
</html>
"""
    
    return send_email(email, subject, html_body)


def main():
    """Main execution flow."""
    print(f"Fuel Price Alert - {datetime.now().isoformat()}")
    print("=" * 50)
    
    # Fetch and parse ACCC page
    print("Fetching ACCC page...")
    try:
        html = fetch_accc_page()
    except Exception as e:
        print(f"Error fetching page: {e}")
        return 1
    
    # Extract buying tips
    print("Extracting buying tips...")
    tips = extract_buying_tips_v2(html)
    
    if not any(tips.values()):
        print("Warning: Could not extract any buying tips. Page structure may have changed.")
        # Fall back to simpler extraction
        tips = extract_buying_tips(html)
    
    # Load previous state
    previous_state = load_state()
    current_state = {}
    
    # Classify each city
    print("\nCity Status:")
    print("-" * 30)
    
    transitions = []
    
    for city in CITIES:
        tip = tips.get(city, "")
        phase = classify_phase(tip)
        current_state[city] = phase
        
        prev = previous_state.get(city, "UNKNOWN")
        
        # Check for WAIT -> BUY transition
        if prev == "WAIT" and phase == "BUY":
            transitions.append(city)
            marker = " 🔔 ALERT!"
        elif prev == "UNKNOWN" and phase == "BUY":
            # First run and already at BUY - don't alert
            marker = " (initial state)"
        else:
            marker = ""
        
        print(f"  {city.capitalize():12} {prev:8} → {phase:8}{marker}")
        
        if tip:
            # Print truncated tip for debugging
            short_tip = tip[:80] + "..." if len(tip) > 80 else tip
            print(f"    \"{short_tip}\"")
    
    # Save current state
    save_state(current_state)
    
    # Send alerts for transitions
    if transitions:
        print(f"\n🔔 Sending alerts for: {', '.join(t.capitalize() for t in transitions)}")
        subscribers = load_subscribers()
        
        for city in transitions:
            city_subs = subscribers.get(city, [])
            tip = tips.get(city, "")
            
            print(f"\n{city.capitalize()}: {len(city_subs)} subscribers")
            
            for email in city_subs:
                send_buy_alert(email, city, tip)
    else:
        print("\nNo transitions detected. No alerts sent.")
    
    print("\n✓ Done")
    return 0


if __name__ == "__main__":
    exit(main())
