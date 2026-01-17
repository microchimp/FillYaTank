#!/usr/bin/env python3
"""
Subscription confirmation and unsubscription handler.

This can be deployed as:
- Vercel serverless function (api/confirm.py)
- Netlify function
- AWS Lambda
- Or run as a simple Flask/FastAPI app

For the simplest MVP, you can also handle confirmations manually
by checking a form submission service and updating subscribers.json
"""

import json
import os
import hashlib
import base64
from pathlib import Path

# These would come from environment variables in production
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
DATA_DIR = Path(__file__).parent.parent / "data"
CITIES = ["sydney", "melbourne", "brisbane", "adelaide", "perth"]


def generate_token(email: str, city: str, action: str) -> str:
    """Generate a secure token for email actions."""
    data = f"{email}|{city}|{action}|{SECRET_KEY}"
    hash_bytes = hashlib.sha256(data.encode()).digest()[:16]
    return base64.urlsafe_b64encode(hash_bytes).decode().rstrip("=")


def verify_token(email: str, city: str, token: str, action: str) -> bool:
    """Verify a token is valid."""
    expected = generate_token(email, city, action)
    return token == expected


def load_subscribers() -> dict[str, list[str]]:
    """Load subscribers grouped by city."""
    subs_file = DATA_DIR / "subscribers.json"
    if subs_file.exists():
        with open(subs_file) as f:
            return json.load(f)
    return {city: [] for city in CITIES}


def save_subscribers(subscribers: dict[str, list[str]]) -> None:
    """Save subscribers to file."""
    DATA_DIR.mkdir(exist_ok=True)
    subs_file = DATA_DIR / "subscribers.json"
    with open(subs_file, "w") as f:
        json.dump(subscribers, f, indent=2)


def confirm_subscription(email: str, city: str, token: str) -> tuple[bool, str]:
    """
    Confirm a subscription if token is valid.
    Returns (success, message)
    """
    email = email.lower().strip()
    city = city.lower().strip()
    
    # Validate inputs
    if city not in CITIES:
        return False, "Invalid city"
    
    if not verify_token(email, city, token, "confirm"):
        return False, "Invalid or expired confirmation link"
    
    # Load current subscribers
    subscribers = load_subscribers()
    
    # Check if already subscribed
    if email in subscribers.get(city, []):
        return True, "You're already subscribed"
    
    # Add subscriber
    if city not in subscribers:
        subscribers[city] = []
    subscribers[city].append(email)
    
    # Save
    save_subscribers(subscribers)
    
    return True, "You're subscribed! You'll only hear from us when prices hit bottom."


def unsubscribe(email: str, city: str, token: str) -> tuple[bool, str]:
    """
    Unsubscribe an email if token is valid.
    Returns (success, message)
    """
    email = email.lower().strip()
    city = city.lower().strip()
    
    # Validate inputs
    if city not in CITIES:
        return False, "Invalid city"
    
    if not verify_token(email, city, token, "unsubscribe"):
        return False, "Invalid unsubscribe link"
    
    # Load current subscribers
    subscribers = load_subscribers()
    
    # Remove if present
    if city in subscribers and email in subscribers[city]:
        subscribers[city].remove(email)
        save_subscribers(subscribers)
        return True, "You've been unsubscribed"
    
    return True, "You weren't subscribed"


# ============================================================
# Vercel Serverless Function Handler
# ============================================================

def handler(request):
    """
    Vercel serverless function handler.
    
    Expects query parameters:
    - action: "confirm" or "unsubscribe"
    - email: subscriber email
    - city: city name
    - token: verification token
    """
    from urllib.parse import parse_qs, urlparse
    
    # Parse query parameters
    parsed = urlparse(request.url)
    params = parse_qs(parsed.query)
    
    action = params.get("action", [""])[0]
    email = params.get("email", [""])[0]
    city = params.get("city", [""])[0]
    token = params.get("token", [""])[0]
    
    if not all([action, email, city, token]):
        return {
            "statusCode": 400,
            "body": "Missing parameters"
        }
    
    if action == "confirm":
        success, message = confirm_subscription(email, city, token)
    elif action == "unsubscribe":
        success, message = unsubscribe(email, city, token)
    else:
        return {
            "statusCode": 400,
            "body": "Invalid action"
        }
    
    # Return a simple HTML page
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fuel Alert</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 480px;
                margin: 80px auto;
                padding: 24px;
                text-align: center;
            }}
            .message {{
                font-size: 18px;
                margin-bottom: 24px;
            }}
            a {{
                color: #16a34a;
            }}
        </style>
    </head>
    <body>
        <p class="message">{message}</p>
        <p><a href="/">← Back to Fuel Alert</a></p>
    </body>
    </html>
    """
    
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": html
    }


# ============================================================
# Flask App (alternative deployment)
# ============================================================

def create_flask_app():
    """Create a Flask app for handling subscriptions."""
    from flask import Flask, request, redirect
    
    app = Flask(__name__)
    
    @app.route("/confirm")
    def confirm_route():
        email = request.args.get("email", "")
        city = request.args.get("city", "")
        token = request.args.get("token", "")
        
        success, message = confirm_subscription(email, city, token)
        
        return f"""
        <html>
        <body style="font-family: sans-serif; max-width: 480px; margin: 80px auto; text-align: center;">
            <p style="font-size: 18px;">{message}</p>
            <p><a href="/">← Back</a></p>
        </body>
        </html>
        """
    
    @app.route("/unsubscribe")
    def unsubscribe_route():
        email = request.args.get("email", "")
        city = request.args.get("city", "")
        token = request.args.get("token", "")
        
        success, message = unsubscribe(email, city, token)
        
        return f"""
        <html>
        <body style="font-family: sans-serif; max-width: 480px; margin: 80px auto; text-align: center;">
            <p style="font-size: 18px;">{message}</p>
        </body>
        </html>
        """
    
    return app


if __name__ == "__main__":
    # Run Flask app locally for testing
    app = create_flask_app()
    app.run(debug=True, port=5000)
