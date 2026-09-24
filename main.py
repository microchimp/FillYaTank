#!/usr/bin/env python3
"""
FillYaTank: petrol price cycle alerts
Scrapes ACCC petrol price cycles page and sends email alerts
when prices hit the bottom of the cycle.

Inspired by "How They Get You" by Chris Kohler
"""

import json
import os
import re
import hashlib
import hmac
import base64
from datetime import datetime, timedelta
from html import escape, unescape
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# Configuration
ACCC_URL = "https://www.accc.gov.au/consumers/petrol-and-fuel/petrol-price-cycles-in-the-5-largest-cities"
CITIES = ["sydney", "melbourne", "brisbane", "adelaide", "perth"]
DATA_DIR = Path(__file__).parent / "data"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alerts@yourdomain.com")
SITE_URL = os.environ.get("SITE_URL", "https://fillyatank.app")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
WORKER_URL = os.environ.get("WORKER_URL", "https://api.fillyatank.app")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

# Test mode: force a WAIT -> BUY transition for one city, email only TEST_EMAIL,
# and leave state.json untouched. Triggered manually from the workflow.
SIMULATE_BUY_CITY = os.environ.get("SIMULATE_BUY_CITY", "").lower().strip()
TEST_EMAIL = os.environ.get("TEST_EMAIL", "").lower().strip()

# Owner stats summary: sent on Monday scheduled runs, or on demand from the workflow.
# Goes to the TEST_EMAIL secret (the owner's address).
STATS_REPORT = os.environ.get("STATS_REPORT", "").lower() == "true"

# Quiet period: eastern price cycles have stopped, so there's nothing worth a
# weekly email. Routine owner emails (the stats summary, notices about new ACCC
# wording) are held back. Things the owner still needs to hear come through:
# cycles restarting, a possible BUY awaiting confirmation, and a broken scrape.
# Set to False when cycles restart to get the weekly summary back.
QUIET_PERIOD = True

# Debug mode: classify this text (rules, then AI if unclear) and exit. No side effects.
CLASSIFY_TEXT = os.environ.get("CLASSIFY_TEXT", "").strip()


def fetch_accc_page() -> str:
    """Fetch the ACCC petrol price cycles page."""
    # No custom User-Agent: the ACCC's CDN rejects unrecognised agents with 403
    response = requests.get(ACCC_URL, timeout=30)
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
            tip_text = unescape(tip_text)  # Decode entities like &nbsp;
            tip_text = re.sub(r"\s+", " ", tip_text)  # Normalize whitespace
            tip_text = tip_text.strip()
            tips[city] = tip_text
        else:
            tips[city] = ""
    
    return tips


# ACCC boilerplate that contains misleading words ("lowest prices", "buy petrol",
# "not yet increased") in otherwise-WAIT tips. Removed before matching.
TIP_BOILERPLATE = [
    r"shop around,? for (the )?(lowest prices|lower[- ]priced retailers)",
    r"find lower[- ]priced retailers",
    r"retailers (who|that) have not yet increased (their )?prices",
    r"motorists looking to buy petrol",
]

# Prices at the bottom of the cycle
BUY_PATTERNS = [
    r"\b(lowest|low|bottom)\s+point\b",
    r"\b(around|at|near)\s+(or near\s+)?(the|its|their)\s+(lowest|bottom)\b",
    r"\bbottom of the (price )?cycle\b",
    r"\bbottomed\b",
    r"\bgood time (for motorists )?to (buy|fill)",
    r"\bnow is a good time\b",
]

# Prices moving, or at the top of the cycle
WAIT_PATTERNS = [
    r"\bincreas(e|es|ed|ing)\b",
    r"\bdecreas(e|es|ed|ing)\b",
    r"\b(rise|rises|rising|rose|climb|climbing)\b",
    r"\b(fall|falls|falling|fell|drop|drops|dropping|dropped)\b",
    r"\b(high|highest|peak)\b",
]

NEGATION = r"\b(not|no longer|isn't|aren't|yet to)\b"


def normalise_tip(tip_text: str) -> str:
    return " ".join(unescape(tip_text).replace("\xa0", " ").lower().split())


def classify_tip(tip_text: str) -> tuple[str, str]:
    """
    Classify a buying tip with keyword rules.
    
    Returns (phase, reason) where phase is BUY, WAIT or UNCLEAR. UNCLEAR means
    the rules can't decide safely: no known signal, or BUY and WAIT/negation
    signals together (e.g. "near the lowest point but may fall further").
    """
    text = normalise_tip(tip_text)
    if not text:
        return "UNCLEAR", "empty tip (extraction may have failed)"
    
    for pattern in TIP_BOILERPLATE:
        text = re.sub(pattern, " ", text)
    
    buy = [p for p in BUY_PATTERNS if re.search(p, text)]
    wait = [p for p in WAIT_PATTERNS if re.search(p, text)]
    negated = re.search(NEGATION, text) is not None
    
    if buy and not wait and not negated:
        return "BUY", "at-bottom wording"
    if wait and not buy:
        return "WAIT", "rising, falling or high wording"
    if buy:
        return "UNCLEAR", "mixed BUY and WAIT/negation wording"
    return "UNCLEAR", "no known wording"


def classify_phase(tip_text: str) -> str:
    """Rules-only BUY/WAIT (UNCLEAR counts as WAIT, the safe default)."""
    phase, _ = classify_tip(tip_text)
    return "BUY" if phase == "BUY" else "WAIT"


def load_wordings() -> dict:
    """AI decisions for wordings the rules couldn't classify, keyed by normalised text."""
    wordings_file = DATA_DIR / "wordings.json"
    if wordings_file.exists():
        with open(wordings_file) as f:
            return json.load(f)
    return {}


def save_wordings(wordings: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "wordings.json", "w") as f:
        json.dump(wordings, f, indent=2, sort_keys=True)


def ai_classify(tip_text: str) -> str:
    """Ask the Worker's free Workers AI model: BUY, WAIT or UNSURE."""
    response = requests.post(
        f"{WORKER_URL}/?action=classify",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        json={"text": tip_text[:1000]},
        timeout=60
    )
    response.raise_for_status()
    return response.json()["phase"]


def resolve_phase(city: str, tip: str, wordings: dict) -> tuple[str, str, bool]:
    """
    Rules first; AI only for unclear wording, with each answer cached.
    Returns (BUY|WAIT, how it was decided, whether this wording is new).
    Anything uncertain resolves to WAIT, the safe default.
    """
    phase, reason = classify_tip(tip)
    if phase != "UNCLEAR":
        return phase, f"rules: {reason}", False
    
    key = normalise_tip(tip)
    if not key:
        return "WAIT", f"rules: {reason}", False
    
    if key in wordings:
        cached = wordings[key]["phase"]
        # Only an owner-confirmed BUY sends alerts; UNCONFIRMED_BUY stays WAIT
        return ("BUY" if cached == "BUY" else "WAIT"), f"saved answer: {cached}", False
    
    if not ADMIN_TOKEN:
        return "WAIT", f"rules: {reason}; AI unavailable (no ADMIN_TOKEN)", False
    
    try:
        ai_phase = ai_classify(tip)
    except Exception as e:
        # Don't cache failures; try again next run
        return "WAIT", f"rules: {reason}; AI call failed ({e})", False
    
    # Never alert subscribers on an AI guess: a BUY waits for the owner to confirm it
    saved_phase = "UNCONFIRMED_BUY" if ai_phase == "BUY" else ai_phase
    wordings[key] = {"phase": saved_phase, "first_seen": datetime.utcnow().strftime("%Y-%m-%d"), "city": city}
    return "WAIT", f"AI: {ai_phase} ({reason})", True


def notify_owner(subject: str, body_html: str, routine: bool = True) -> None:
    """Email the owner (TEST_EMAIL secret) about something that needs attention.

    Routine notices are held back during the quiet period; pass routine=False
    for anything the owner would want during it.
    """
    if not TEST_EMAIL:
        print(f"Owner notice (no TEST_EMAIL set): {subject}")
        return
    if routine and QUIET_PERIOD:
        print(f"Owner notice (quiet period, not sent): {subject}")
        return
    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
{body_html}
</body>
</html>"""
    send_email(TEST_EMAIL, subject, html_body)


def notify_new_wording(city: str, tip: str, decision: str, how: str) -> None:
    """Tell the owner the ACCC used wording the rules didn't recognise."""
    ai_says_buy = how.startswith("AI: BUY")
    if ai_says_buy:
        action = ("<strong>The AI thinks this means BUY, but no alerts were sent.</strong> "
                  "If it's right, change <code>UNCONFIRMED_BUY</code> to <code>BUY</code> for this wording in "
                  "<code>data/wordings.json</code> on GitHub, and the next check will alert subscribers.")
        subject = f"🆕 Confirm needed: new ACCC wording for {city.capitalize()} may mean BUY"
    else:
        action = (f"Treated as <strong>{decision}</strong>. The answer is saved in <code>data/wordings.json</code>; "
                  "edit it there if it's wrong.")
        subject = f"🆕 New ACCC wording for {city.capitalize()}: treated as {decision}"
    notify_owner(subject, f"""
    <h2 style="margin: 0 0 16px 0;">New ACCC wording for {city.capitalize()}</h2>
    <p style="font-size: 16px; line-height: 1.6; margin: 0 0 16px 0; padding: 12px 16px; background: #f5f5f5; border-radius: 6px;">“{escape(tip)}”</p>
    <p style="font-size: 16px; line-height: 1.6; margin: 0 0 8px 0;">{action}</p>
    <p style="font-size: 14px; color: #666; line-height: 1.6; margin: 16px 0 0 0;">How it was decided: {escape(how)}</p>""",
                 routine=not ai_says_buy)  # a possible BUY is a cycle-restart signal: always send


EASTERN_CITIES = ["sydney", "melbourne", "brisbane", "adelaide"]
PAUSED_PHRASE = "have mostly not occurred"


def cycle_signals(html: str) -> dict:
    """
    Signals that eastern price cycles have restarted:
    - whether the ACCC still shows its 'cycles have mostly not occurred' note
    - each city's latest completed cycle in the ACCC's 'past 5 price cycles'
      table (the next low = first day + total days); a later date means the
      ACCC has recorded a new cycle
    """
    soup = BeautifulSoup(html, "html.parser")
    signals = {"paused_note": PAUSED_PHRASE in soup.get_text(" "), "latest_low": {}}
    for city in EASTERN_CITIES:
        heading = next((h for h in soup.find_all(["h2", "h3"])
                        if h.get_text(" ", strip=True).lower() == f"petrol prices in {city}"), None)
        table = heading.find_next("table") if heading else None
        latest = None
        for row in (table.find_all("tr") if table else []):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            try:
                start = datetime.strptime(cells[0], "%a %d %b %y").date()
                low = start + timedelta(days=int(cells[4]))
            except (IndexError, ValueError):
                continue
            latest = max(latest or low, low)
        signals["latest_low"][city] = latest.isoformat() if latest else None
    return signals


def watch_cycles(html: str, current_state: dict) -> None:
    """Email the owner the first time eastern cycles show signs of restarting."""
    path = DATA_DIR / "cycle_watch.json"
    previous = json.loads(path.read_text()) if path.exists() else None
    signals = cycle_signals(html)

    changes = []
    if previous:
        if previous.get("paused_note") and not signals["paused_note"]:
            changes.append("The ACCC has removed its note that cycles have mostly not occurred since the conflict began.")
        for city in EASTERN_CITIES:
            before, now = previous.get("latest_low", {}).get(city), signals["latest_low"].get(city)
            if now and before and now > before:
                changes.append(f"{city.capitalize()}: the ACCC recorded a new completed cycle (latest low {now}, was {before}).")
    for city in EASTERN_CITIES:
        if current_state.get(city) == "BUY" and (previous or {}).get("buy", {}).get(city) != "BUY":
            changes.append(f"{city.capitalize()}: the ACCC says prices are around the lowest point of the cycle.")
    signals["buy"] = {city: current_state.get(city) for city in EASTERN_CITIES}

    if changes:
        print("\n🔔 Cycle watch: " + " | ".join(changes))
        items = "".join(f"<li>{escape(c)}</li>" for c in changes)
        notify_owner("🔔 FillYaTank: eastern petrol price cycles may be back", f"""
    <h2 style="margin: 0 0 16px 0;">Price cycles may be restarting</h2>
    <ul style="font-size: 16px; line-height: 1.6;">{items}</ul>
    <p style="font-size: 14px; color: #666; line-height: 1.6;">Check the <a href="{ACCC_URL}">ACCC petrol price cycles page</a>. Good moment for a launch post in that city.</p>
    <p style="font-size: 14px; color: #666; line-height: 1.6;">Weekly stats emails are paused: set <code>QUIET_PERIOD = False</code> in <code>main.py</code> to start them again.</p>""",
                     routine=False)
    elif previous is None:
        print("\nCycle watch: baseline recorded")
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(signals, indent=2) + "\n")


def load_state() -> dict:
    """Load the previous state from file."""
    state_file = DATA_DIR / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {city: "UNKNOWN" for city in CITIES}


def short_tip(tip_text: str) -> str:
    """First clause of an ACCC tip, for the site: 'prices have increased motorists ...' -> 'Prices have increased'."""
    text = normalise_tip(tip_text)
    text = re.split(r"[.;,]| motorists | if | now is | we encourage ", text)[0]
    text = re.sub(r"^while ", "", " ".join(text.split()))
    return text[:1].upper() + text[1:] if text else ""


def save_tips(tips: dict[str, str]) -> None:
    """Short ACCC wording per city, shown under each city on the site."""
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "tips.json", "w") as f:
        json.dump({city: short_tip(tips.get(city, "")) for city in CITIES}, f, indent=2)


def save_state(state: dict) -> None:
    """Save the current state to file."""
    DATA_DIR.mkdir(exist_ok=True)
    state_file = DATA_DIR / "state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def load_subscribers() -> dict[str, list[str]]:
    """Load subscribers grouped by city from the signup Worker (falls back to local file)."""
    if ADMIN_TOKEN:
        response = requests.get(
            f"{WORKER_URL}/?action=subscribers",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    subs_file = DATA_DIR / "subscribers.json"
    if subs_file.exists():
        with open(subs_file) as f:
            return json.load(f)
    return {city: [] for city in CITIES}


def generate_token(email: str, city: str, action: str = "unsubscribe") -> str:
    """Generate a secure token for email actions."""
    data = f"{email}|{city}|{action}"
    hash_bytes = hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(hash_bytes).decode().rstrip("=")


def verify_token(email: str, city: str, token: str, action: str = "unsubscribe") -> bool:
    """Verify a token is valid."""
    expected = generate_token(email, city, action)
    return hmac.compare_digest(token, expected)


def mask_email(email: str) -> str:
    """Hide most of an address for public Actions logs."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def send_email(to_email: str, subject: str, html_body: str, headers: dict | None = None, text_body: str | None = None) -> bool:
    """Send an email via Resend API."""
    if not RESEND_API_KEY:
        print(f"[DRY RUN] Would send to {mask_email(to_email)}: {subject}")
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
            "html": html_body,
            **({"text": text_body} if text_body else {}),
            "headers": headers or {}
        },
        timeout=30
    )
    
    if response.status_code == 200:
        print(f"✓ Sent to {mask_email(to_email)} from @{FROM_EMAIL.partition('@')[2]} (Resend id {response.json().get('id')})")
        return True
    else:
        print(f"✗ Failed to send to {mask_email(to_email)}: {response.text}")
        return False


FORWARD_URL = "https://fillyatank.app/?ref=fwd"


def filled_link(email: str, city: str) -> str:
    """Signed 'I filled my tank' link. u is an anonymous id, never the email itself."""
    u = base64.urlsafe_b64encode(
        hmac.new(SECRET_KEY.encode(), f"subscriber|{email}".encode(), hashlib.sha256).digest()[:12]
    ).decode().rstrip("=")
    day = datetime.now(ZoneInfo("Australia/Sydney")).strftime("%Y-%m-%d")
    token = generate_token(u, city, f"{day}|filled")
    return f"{SITE_URL}/filled.html?city={city}&d={day}&u={u}&t={token}"


def send_alert(email: str, city: str, subject: str, headline: str, details: list[str]) -> bool:
    """Send a fill-up alert (HTML and plain text) with one-click unsubscribe."""
    unsubscribe_token = generate_token(email, city)
    unsubscribe_url = f"{SITE_URL}/unsubscribe.html?email={quote(email)}&city={city}&token={unsubscribe_token}"
    one_click_url = f"{WORKER_URL}/?action=unsubscribe&email={quote(email)}&city={city}&token={unsubscribe_token}"
    # RFC 8058 one-click unsubscribe, expected by Gmail and Yahoo
    list_headers = {
        "List-Unsubscribe": f"<{one_click_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"
    }
    if SIMULATE_BUY_CITY or os.environ.get("SIMULATE_PERTH_JUMP", "").lower() == "true":
        subject = f"[TEST] {subject}"

    filled_url = filled_link(email, city)
    detail_html = "".join(
        f'<p style="font-size: 15px; line-height: 1.6; color: #444; margin: 0 0 10px 0;">{escape(line)}</p>'
        for line in details
    )
    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
    <p style="font-size: 18px; line-height: 1.6; margin: 0 0 20px 0;">{escape(headline)}</p>
    <p style="font-size: 26px; font-weight: 700; margin: 0 0 20px 0; color: #1e7d46;">Time to fill ya tank!</p>
    {detail_html}
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 22px 0 6px 0;">
        <tr><td style="border-radius: 8px; background: #1e7d46;">
            <a href="{filled_url}" style="display: inline-block; padding: 12px 22px; font-size: 16px; font-weight: 700; color: #ffffff; text-decoration: none; border-radius: 8px;">⛽ I filled my tank</a>
        </td></tr>
    </table>
    <p style="font-size: 13px; color: #888; margin: 0;">Tap after you fill up. It helps us see if FillYaTank is working.</p>
    <p style="font-size: 15px; line-height: 1.6; margin: 20px 0 0 0;">
        Know someone who drives? <a href="{FORWARD_URL}" style="color: #1e7d46;">Forward this to a mate</a>. It's free.
    </p>
    <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 28px 0;">
    <p style="font-size: 13px; color: #666; margin: 0 0 8px 0;">
        You're getting this because you signed up for {city.capitalize()} alerts at fillyatank.app.
        <a href="{unsubscribe_url}" style="color: #666;">Unsubscribe</a>
    </p>
    <p style="font-size: 13px; color: #999; margin: 0; font-style: italic;">Inspired by "How They Get You" by Chris Kohler</p>
</body>
</html>"""
    text_body = "\n\n".join([
        headline,
        "Time to fill ya tank!",
        *details,
        f"Filled up? Let us know: {filled_url}",
        f"Know someone who drives? Forward this to a mate: {FORWARD_URL}",
        f"You're getting this because you signed up for {city.capitalize()} alerts at fillyatank.app.\nUnsubscribe: {unsubscribe_url}",
    ])
    return send_email(email, subject, html_body, list_headers, text_body)


def send_buy_alert(email: str, city: str, tip_text: str) -> bool:
    """ACCC-based alert: the buying tip says prices are at the bottom."""
    details = []
    if tip_text:
        details.append(f"The ACCC's latest buying tip for {city.capitalize()}: \"{normalise_tip(tip_text)}\"")
    details.append("Prices usually climb again soon after the bottom, so the sooner the better.")
    return send_alert(
        email, city,
        subject=f"⛽ {city.capitalize()} petrol prices are at the bottom",
        headline="Prices have hit the low point of the cycle.",
        details=details,
    )


def send_stats_report(days: int = 7) -> bool:
    """Email the owner anonymous visit and signup counts from the Worker."""
    if not (ADMIN_TOKEN and TEST_EMAIL):
        print("Stats report skipped: ADMIN_TOKEN or TEST_EMAIL not set")
        return False
    
    response = requests.get(
        f"{WORKER_URL}/?action=stats&days={days}",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=30
    )
    response.raise_for_status()
    stats = response.json()
    
    events = ["views", "signups", "confirmations", "unsubscribes", "filled"]
    totals = {event: sum(day[event] for day in stats["daily"]) for event in events}
    total_subscribers = sum(stats["subscribersByCity"].values())
    
    cell = 'style="padding: 6px 10px; border-bottom: 1px solid #e5e5e5; text-align: right;"'
    head = 'style="padding: 6px 10px; border-bottom: 2px solid #1a1a1a; text-align: right;"'
    rows = "".join(
        f"<tr><td {cell.replace('right', 'left')}>{day['date']}</td>"
        + "".join(f"<td {cell}>{day[event]}</td>" for event in events)
        + "</tr>"
        for day in stats["daily"]
    )
    refs = stats.get("refs") or {}
    ref_rows = "".join(
        f"<tr><td {cell.replace('right', 'left')}>{escape(ref)}</td><td {cell}>{count}</td></tr>"
        for ref, count in sorted(refs.items(), key=lambda item: -item[1])
    ) or f"<tr><td {cell.replace('right', 'left')} colspan='2'>No tagged visits yet (links with ?ref=...)</td></tr>"
    city_rows = "".join(
        f"<tr><td {cell.replace('right', 'left')}>{city.capitalize()}</td><td {cell}>{count}</td></tr>"
        for city, count in stats["subscribersByCity"].items()
    )
    
    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
    <h2 style="margin: 0 0 8px 0;">FillYaTank — last {days} days</h2>
    <p style="font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
        <strong>{totals['views']}</strong> homepage views ·
        <strong>{totals['signups']}</strong> sign-ups ·
        <strong>{totals['confirmations']}</strong> confirmed ·
        <strong>{totals['unsubscribes']}</strong> unsubscribed ·
        <strong>{totals['filled']}</strong> filled up<br>
        <strong>{total_subscribers}</strong> subscribers in total
    </p>
    <table style="border-collapse: collapse; font-size: 14px; margin: 0 0 24px 0;">
        <tr><th {head.replace('right', 'left')}>Date</th><th {head}>Views</th><th {head}>Sign-ups</th><th {head}>Confirmed</th><th {head}>Unsubscribed</th><th {head}>Filled up</th></tr>
        {rows}
    </table>
    <table style="border-collapse: collapse; font-size: 14px; margin: 0 0 24px 0;">
        <tr><th {head.replace('right', 'left')}>Visits by source</th><th {head}>Views</th></tr>
        {ref_rows}
    </table>
    <table style="border-collapse: collapse; font-size: 14px;">
        <tr><th {head.replace('right', 'left')}>City</th><th {head}>Subscribers</th></tr>
        {city_rows}
    </table>
    <p style="font-size: 13px; color: #999; margin: 24px 0 0 0;">
        Anonymous counts only: no cookies, IP addresses or identifiers. Views are counted when the homepage loads in a browser, so most bots are excluded. Dates are Sydney time.
    </p>
</body>
</html>
"""
    
    print(f"\n📊 Stats report: {totals['views']} views, {totals['signups']} sign-ups, "
          f"{totals['confirmations']} confirmed, {total_subscribers} subscribers")
    return send_email(TEST_EMAIL, f"📊 FillYaTank weekly stats: {totals['views']} views, {totals['confirmations']} new subscribers", html_body)


def main():
    """Main execution flow."""
    print(f"FillYaTank price check - {datetime.now().isoformat()}")
    print("=" * 50)
    
    if RESEND_API_KEY and SECRET_KEY == "change-this-in-production":
        print("Error: SECRET_KEY is not set; refusing to send emails with forgeable unsubscribe links")
        return 1
    
    if STATS_REPORT:
        return 0 if send_stats_report() else 1
    
    if CLASSIFY_TEXT:
        phase, how, _ = resolve_phase("test", CLASSIFY_TEXT, {})
        print(f"Text: {CLASSIFY_TEXT!r}\nDecision: {phase} ({how})")
        return 0
    
    if SIMULATE_BUY_CITY:
        if SIMULATE_BUY_CITY not in CITIES or not TEST_EMAIL:
            print("Error: simulation needs a valid city and the TEST_EMAIL secret")
            return 1
        print(f"🧪 TEST MODE: simulating WAIT → BUY for {SIMULATE_BUY_CITY.capitalize()}")
    
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
    
    # A broken scrape must not quietly turn every city into WAIT
    empty = [city for city in CITIES if not tips.get(city, "").strip()]
    if len(empty) >= 2:
        print(f"Error: no buying tip found for {', '.join(empty)}. The ACCC page may have changed.")
        if not SIMULATE_BUY_CITY:
            notify_owner("⚠️ FillYaTank: couldn't read the ACCC buying tips", f"""
    <h2 style="margin: 0 0 16px 0;">The ACCC page couldn't be read</h2>
    <p style="font-size: 16px; line-height: 1.6;">No buying tip was found for: <strong>{', '.join(c.capitalize() for c in empty)}</strong>.
    The page layout may have changed. State wasn't updated and no alerts were sent.</p>
    <p style="font-size: 14px; color: #666; line-height: 1.6;">Check the latest "Fuel Price Check" run on GitHub and the ACCC page.</p>""",
                         routine=False)
        return 1
    
    # Load previous state
    previous_state = load_state()
    current_state = {}
    wordings = load_wordings()
    
    # Classify each city
    print("\nCity Status:")
    print("-" * 30)
    
    transitions = []
    failures = 0
    
    for city in CITIES:
        tip = tips.get(city, "")
        phase, how, new_wording = resolve_phase(city, tip, wordings)
        current_state[city] = phase
        if new_wording and not SIMULATE_BUY_CITY:
            print(f"  🆕 New wording for {city.capitalize()}: {how}")
            notify_new_wording(city, tip, phase, how)
        elif not how.startswith("rules: rising") and not how.startswith("rules: at-bottom"):
            print(f"  ℹ️  {city.capitalize()}: {how}")
        
        prev = previous_state.get(city, "UNKNOWN")
        
        if city == SIMULATE_BUY_CITY:
            prev, phase = "WAIT", "BUY"
        
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
    
    # Save current state (never in test mode)
    if not SIMULATE_BUY_CITY:
        save_state(current_state)
        save_wordings(wordings)
        save_tips(tips)
        try:
            watch_cycles(html, current_state)
        except Exception as e:
            print(f"Warning: cycle watch failed: {e}")
    
    # Send alerts for transitions
    if transitions:
        print(f"\n🔔 Sending alerts for: {', '.join(t.capitalize() for t in transitions)}")
        subscribers = load_subscribers()
        
        for city in transitions:
            if city == "perth" and not SIMULATE_BUY_CITY:
                print("\nPerth: skipped here; Perth alerts come from FuelWatch's next-day prices (perth_alert.py)")
                continue
            city_subs = subscribers.get(city, [])
            tip = tips.get(city, "")
            
            print(f"\n{city.capitalize()}: {len(city_subs)} subscribers")
            
            if SIMULATE_BUY_CITY:
                city_subs = [email for email in city_subs if email == TEST_EMAIL]
                print(f"  Test mode: sending only to TEST_EMAIL ({len(city_subs)} match)")
                if not city_subs:
                    print("  Error: TEST_EMAIL is not subscribed to this city")
                    return 1
            
            for email in city_subs:
                if not send_buy_alert(email, city, tip):
                    failures += 1
    else:
        print("\nNo transitions detected. No alerts sent.")
    
    # Weekly owner summary on the Monday scheduled run, unless it's the quiet
    # period (the workflow's "send stats report" button still works). A failure
    # here must not
    # fail the run, or state.json wouldn't be committed and alerts would repeat.
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and datetime.utcnow().weekday() == 0 and not QUIET_PERIOD:
        try:
            send_stats_report()
        except Exception as e:
            print(f"Warning: stats report failed: {e}")
    
    if failures:
        print(f"\n✗ {failures} alert(s) failed to send")
        return 1
    
    print("\n✓ Done")
    return 0


if __name__ == "__main__":
    exit(main())
