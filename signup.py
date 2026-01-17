#!/usr/bin/env python3
"""
Signup handler - processes new subscription requests.

This script can be:
1. Called manually when you receive form submissions
2. Triggered by a webhook from your form service
3. Run as part of a serverless function

Usage:
    python signup.py <email> <city>
    
Example:
    python signup.py "user@example.com" "sydney"
"""

import sys
import os
import re
import json
import hashlib
import base64
from pathlib import Path

import requests

# Configuration
CITIES = ["sydney", "melbourne", "brisbane", "adelaide", "perth"]
DATA_DIR = Path(__file__).parent / "data"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alerts@yourdomain.com")
SITE_URL = os.environ.get("SITE_URL", "https://yourusername.github.io/fuel-alert")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")


def is_valid_email(email: str) -> bool:
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    if len(email) > 254:
        return False
    return True


def generate_token(email: str, city: str, action: str) -> str:
    """Generate a secure token for email actions."""
    data = f"{email}|{city}|{action}|{SECRET_KEY}"
    hash_bytes = hashlib.sha256(data.encode()).digest()[:16]
    return base64.urlsafe_b64encode(hash_bytes).decode().rstrip("=")


def load_subscribers() -> dict[str, list[str]]:
    """Load subscribers grouped by city."""
    subs_file = DATA_DIR / "subscribers.json"
    if subs_file.exists():
        with open(subs_file) as f:
            return json.load(f)
    return {city: [] for city in CITIES}


def load_state() -> dict[str, str]:
    """Load current price state."""
    state_file = DATA_DIR / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {}


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via Resend API."""
    if not RESEND_API_KEY:
        print(f"[DRY RUN] Would send to {to_email}: {subject}")
        print(f"Body preview: {html_body[:200]}...")
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
        return True
    else:
        print(f"Error sending email: {response.text}")
        return False


def send_confirmation_email(email: str, city: str) -> bool:
    """Send the double opt-in confirmation email."""
    city_display = city.capitalize()
    token = generate_token(email, city, "confirm")
    confirm_url = f"{SITE_URL}/confirm.html?email={email}&city={city}&token={token}"
    
    # Get current status for this city
    state = load_state()
    current_phase = state.get(city, "UNKNOWN")
    
    if current_phase == "BUY":
        status_note = f"<strong>{city_display} prices are currently at the bottom</strong> — fill up today if you can!"
    elif current_phase == "WAIT":
        status_note = f"{city_display} prices are not yet at the bottom. We'll email you when they are."
    else:
        status_note = f"We'll email you when {city_display} prices hit the bottom of the cycle."
    
    subject = "Confirm your Fuel Alert subscription"
    
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
    <p style="font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
        Click to confirm your subscription:
    </p>
    
    <p style="margin: 0 0 32px 0;">
        <a href="{confirm_url}" 
           style="display: inline-block; background: #16a34a; color: white; padding: 12px 24px; 
                  text-decoration: none; border-radius: 6px; font-weight: 500;">
            Confirm subscription
        </a>
    </p>
    
    <p style="font-size: 14px; color: #666; line-height: 1.6; margin: 0 0 24px 0;">
        {status_note}
    </p>
    
    <p style="font-size: 14px; color: #666; line-height: 1.6; margin: 0 0 24px 0;">
        You'll only hear from us when prices hit bottom. That's it.
    </p>
    
    <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 32px 0;">
    
    <p style="font-size: 13px; color: #999; margin: 0; font-style: italic;">
        Inspired by "How They Get You" by Chris Kohler
    </p>
</body>
</html>
"""
    
    return send_email(email, subject, html_body)


def process_signup(email: str, city: str) -> tuple[bool, str]:
    """
    Process a new signup request.
    
    Returns (success, message)
    """
    # Normalize inputs
    email = email.lower().strip()
    city = city.lower().strip()
    
    # Validate email
    if not is_valid_email(email):
        return False, "Invalid email address"
    
    # Validate city
    if city not in CITIES:
        return False, f"Invalid city. Choose from: {', '.join(CITIES)}"
    
    # Check if already subscribed
    subscribers = load_subscribers()
    if email in subscribers.get(city, []):
        return False, "This email is already subscribed"
    
    # Send confirmation email
    if send_confirmation_email(email, city):
        return True, "Check your inbox to confirm"
    else:
        return False, "Failed to send confirmation email"


def main():
    """CLI interface for processing signups."""
    if len(sys.argv) != 3:
        print("Usage: python signup.py <email> <city>")
        print(f"Cities: {', '.join(CITIES)}")
        sys.exit(1)
    
    email = sys.argv[1]
    city = sys.argv[2]
    
    success, message = process_signup(email, city)
    
    if success:
        print(f"✓ {message}")
    else:
        print(f"✗ {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
