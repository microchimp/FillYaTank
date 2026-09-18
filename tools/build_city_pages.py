#!/usr/bin/env python3
"""
Generate the city landing pages (perth.html, sydney.html, ...) from one template.

Run after changing the template or copy:  python3 tools/build_city_pages.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLES_VERSION = "23"
SITE_JS_VERSION = "1"

CITIES = {
    "sydney": {
        "name": "Sydney",
        "timing": "Sydney's cycle has typically lasted about 5 weeks, according to the ACCC. Prices jump quickly, then drift down over the following weeks.",
        "how": "We check the ACCC's Sydney buying tip every weekday and email you when it says prices are at the bottom.",
    },
    "melbourne": {
        "name": "Melbourne",
        "timing": "Melbourne's cycle has typically lasted about 6 weeks, according to the ACCC. Prices jump quickly, then drift down over the following weeks.",
        "how": "We check the ACCC's Melbourne buying tip every weekday and email you when it says prices are at the bottom.",
    },
    "brisbane": {
        "name": "Brisbane",
        "timing": "Brisbane's cycle has typically lasted about 6½ weeks, according to the ACCC. Prices jump quickly, then drift down over the following weeks.",
        "how": "We check the ACCC's Brisbane buying tip every weekday and email you when it says prices are at the bottom.",
    },
    "adelaide": {
        "name": "Adelaide",
        "timing": "Adelaide's cycle is short, typically about 2½ weeks according to the ACCC, so the bottom comes around often.",
        "how": "We check the ACCC's Adelaide buying tip every weekday and email you when it says prices are at the bottom.",
    },
    "perth": {
        "name": "Perth",
        "timing": "Perth runs on a weekly cycle: prices usually bottom out on Tuesday and jump on Wednesday, by about 15c a litre in recent weeks (FuelWatch data).",
        "how": "WA stations must lock in tomorrow's prices by 2pm, so we know a jump is coming the day before and email you that afternoon.",
    },
}

TEMPLATE = """<!DOCTYPE html>
<html lang="en-AU">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} petrol price cycle: when to fill up | FillYaTank</title>
    <meta name="description" content="Free email alert when {name} petrol hits the bottom of the price cycle, so you know the cheapest time to fill up. No ads.">
    <link rel="canonical" href="https://fillyatank.app/{slug}">
    <meta name="theme-color" content="#fafaf7">
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="preload" href="/fonts/caveat.woff2" as="font" type="font/woff2" crossorigin>
    <link rel="stylesheet" href="/styles.css?v={styles_version}">

    <meta property="og:type" content="website">
    <meta property="og:site_name" content="FillYaTank">
    <meta property="og:url" content="https://fillyatank.app/{slug}">
    <meta property="og:title" content="{name} petrol price cycle: know when to fill up">
    <meta property="og:description" content="One free email when {name} petrol hits the bottom of the cycle. No ads.">
    <meta property="og:image" content="https://fillyatank.app/og-image.png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta name="twitter:card" content="summary_large_image">
</head>
<body>
    <a class="skip-link" href="#main">Skip to content</a>

    <div class="buy-banner hidden" id="buyBanner" role="status">
        <div class="wrap"><span id="buyBannerText"></span></div>
    </div>

    <header class="site-header">
        <div class="wrap">
            <a class="brand" href="/" aria-label="FillYaTank home">
                <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
                    <rect width="32" height="32" rx="8" fill="#1e7d46"/>
                    <path d="M5 10 L14 20 L16.5 8 L25 21" fill="none" stroke="#fff" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
                    <circle cx="25" cy="21" r="3.4" fill="#fff"/>
                </svg>
                FillYaTank
            </a>
        </div>
    </header>

    <main id="main">
        <section class="hero city-hero">
            <div class="wrap hero-grid">
                <div>
                    <h1>{name} petrol price cycle</h1>
                    <p class="lead">Know the cheapest time to fill up in {name}. We email you when prices hit the bottom.</p>

                    <form class="signup" id="signupForm" action="https://api.fillyatank.app/" method="POST">
                        <div class="field-row">
                            <div class="field">
                                <label for="email">Email</label>
                                <input type="email" id="email" name="email" required placeholder="you@example.com" autocomplete="email" inputmode="email">
                            </div>
                            <div class="field">
                                <label for="city">Your city</label>
                                <select id="city" name="city" required>
{options}
                                </select>
                            </div>
                        </div>

                        <!-- Honeypot: hidden from people, filled in by bots -->
                        <div class="hp-field" aria-hidden="true">
                            <label for="website">Website</label>
                            <input type="text" id="website" name="website" tabindex="-1" autocomplete="off">
                        </div>

                        <button class="button" type="submit" id="submitBtn">Email me when to fill up</button>
                        <p class="form-promise">Free. One email per cycle. Unsubscribe in one click.</p>
                        <div class="form-message" id="formMessage" role="status" aria-live="polite"></div>
                    </form>
                </div>

                <div>
                    <h2 class="city-status-title">{name} right now</h2>
                    <div class="status-card">
                        <ul class="status-list">
                            <li class="status-row"><span class="city"><span class="city-name">{name}</span><span class="city-note" data-note="{slug}"></span></span><span class="pill" data-city="{slug}">Checking…</span></li>
                        </ul>
                        <div class="status-footer">
                            <span id="lastChecked"></span>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section class="section tone-white" aria-labelledby="when-title">
            <div class="wrap city-copy">
                <h2 id="when-title">When's the cheapest time to fill up in {name}?</h2>
                <p>{timing}</p>
                <p>{how}</p>
                <p><a href="/#how">See how the price cycle works</a></p>
            </div>
        </section>

        <section class="section tone-tint" aria-labelledby="other-title">
            <div class="wrap city-copy">
                <h2 id="other-title">Other cities</h2>
                <p class="city-links">{other_links}</p>
            </div>
        </section>
    </main>

    <footer class="site-footer">
        <div class="wrap">
            <p>A free project inspired by <em>How They Get You</em> by Chris Kohler.</p>
            <p>Tips from the <a href="https://www.accc.gov.au/consumers/petrol-and-fuel/petrol-price-cycles-in-the-5-largest-cities" rel="noopener">ACCC</a> and FuelWatch. Not affiliated with either.</p>
        </div>
    </footer>

    <script src="/vendor/confetti.browser.js"></script>
    <script src="/site.js?v={site_js_version}"></script>
</body>
</html>
"""


def main() -> None:
    for slug, city in CITIES.items():
        options = "\n".join(
            f'                                    <option value="{s}"{" selected" if s == slug else ""}>{c["name"]}</option>'
            for s, c in CITIES.items()
        )
        other_links = " · ".join(
            f'<a href="/{s}">{c["name"]}</a>' for s, c in CITIES.items() if s != slug
        )
        page = TEMPLATE.format(
            slug=slug,
            name=city["name"],
            timing=city["timing"],
            how=city["how"],
            options=options,
            other_links=other_links,
            styles_version=STYLES_VERSION,
            site_js_version=SITE_JS_VERSION,
        )
        (ROOT / f"{slug}.html").write_text(page)
        print(f"wrote {slug}.html")


if __name__ == "__main__":
    main()
