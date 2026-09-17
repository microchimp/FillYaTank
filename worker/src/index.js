/**
 * FillYaTank Signup Worker
 *
 * POST /                                        signup form -> sends confirmation email
 * GET  /?action=confirm&email&city&ts&token      adds subscriber (link valid 1 hour)
 * GET  /?action=unsubscribe&email&city&token     removes subscriber
 * POST /?action=unsubscribe&email&city&token     RFC 8058 one-click unsubscribe
 * GET  /?action=subscribers (Bearer ADMIN_TOKEN) -> {city: [emails]} for main.py
 * POST /?action=view                             anonymous homepage view count
 * GET  /?action=stats&days=N (Bearer ADMIN_TOKEN) -> daily counts + subscribers per city
 *
 * Stats are aggregate daily counters only: no cookies, IPs or identifiers.
 */

const CITIES = ["sydney", "melbourne", "brisbane", "adelaide", "perth"];
const ALLOWED_ORIGINS = [
  "https://fillyatank.app",
  "https://fillyatank.pages.dev",
  "https://microchimp.github.io"
];
const CONFIRM_LINK_MAX_AGE = 60 * 60; // seconds
const CONFIRM_RESEND_COOLDOWN = 600; // seconds between confirmation emails per address
const STAT_EVENTS = ["views", "signups", "confirmations", "unsubscribes"];
const STATS_RETENTION = 400 * 24 * 60 * 60; // seconds

function sydneyDate(date = new Date()) {
  return date.toLocaleDateString("en-CA", { timeZone: "Australia/Sydney" }); // YYYY-MM-DD
}

// Best effort: KV increments aren't atomic and counting must never break signups.
async function countEvent(env, event) {
  try {
    const key = `stats:${sydneyDate()}:${event}`;
    const current = Number(await env.SUBSCRIBERS.get(key)) || 0;
    await env.SUBSCRIBERS.put(key, String(current + 1), { expirationTtl: STATS_RETENTION });
  } catch (err) {
    // ignore
  }
}

// HMAC-SHA256(SECRET_KEY, "email|city|action"), first 16 bytes, base64url.
// Must match generate_token() in main.py.
async function generateToken(secret, email, city, action) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${email}|${city}|${action}`));
  const bytes = new Uint8Array(sig).slice(0, 16);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function verifyToken(env, email, city, action, token) {
  const expected = await generateToken(env.SECRET_KEY, email, city, action);
  return timingSafeEqual(expected, token || "");
}

function isValidEmail(email) {
  const pattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return pattern.test(email) && email.length <= 254;
}

function corsHeaders(request) {
  const origin = request.headers.get("Origin");
  const headers = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin"
  };
  if (ALLOWED_ORIGINS.includes(origin)) headers["Access-Control-Allow-Origin"] = origin;
  return headers;
}

function json(request, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders(request),
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    }
  });
}

async function sendConfirmationEmail(env, email, city) {
  const ts = Math.floor(Date.now() / 1000);
  const token = await generateToken(env.SECRET_KEY, email, city, `confirm|${ts}`);
  const confirmUrl = `${env.SITE_URL}/confirm.html?email=${encodeURIComponent(email)}&city=${city}&ts=${ts}&token=${token}`;
  const cityDisplay = city.charAt(0).toUpperCase() + city.slice(1);

  const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
  <p style="font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
    Click to confirm your subscription for <strong>${cityDisplay}</strong> fuel alerts:
  </p>
  
  <p style="margin: 0 0 32px 0;">
    <a href="${confirmUrl}" 
       style="display: inline-block; background: #22c55e; color: white; padding: 12px 24px; 
              text-decoration: none; border-radius: 6px; font-weight: 500;">
      Confirm subscription
    </a>
  </p>
  
  <p style="font-size: 14px; color: #666; line-height: 1.6; margin: 0 0 24px 0;">
    This link expires in 1 hour. You'll only hear from us when prices hit bottom. That's it.
  </p>
  
  <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 32px 0;">
  
  <p style="font-size: 13px; color: #999; margin: 0; font-style: italic;">
    Inspired by "How They Get You" by Chris Kohler
  </p>
</body>
</html>
`;

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      from: `FillYaTank <${env.FROM_EMAIL}>`,
      to: [email],
      subject: "Confirm your FillYaTank subscription",
      html: html
    })
  });

  return response.ok;
}

async function handleSignup(request, env, ctx) {
  const formData = await request.formData();
  const email = (formData.get("email") || "").toLowerCase().trim();
  const city = (formData.get("city") || "").toLowerCase().trim();
  const honeypot = formData.get("website") || "";

  // Silently reject bots but return success
  if (honeypot) return json(request, { success: true });

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const { success: withinLimit } = await env.SIGNUP_LIMITER.limit({ key: ip });
  if (!withinLimit) return json(request, { error: "Too many requests. Please try again in a minute." }, 429);

  if (!email || !isValidEmail(email)) return json(request, { error: "Invalid email address" }, 400);
  if (!city || !CITIES.includes(city)) return json(request, { error: "Invalid city" }, 400);

  // Don't let the form be used to flood one inbox. Respond identically either
  // way so the endpoint doesn't reveal anything about the address.
  const cooldownKey = `cooldown:${email}`;
  if (await env.SUBSCRIBERS.get(cooldownKey)) {
    return json(request, { success: true, message: "Check your inbox to confirm" });
  }

  const sent = await sendConfirmationEmail(env, email, city);
  if (!sent) return json(request, { error: "Failed to send email" }, 500);

  await env.SUBSCRIBERS.put(cooldownKey, "1", { expirationTtl: CONFIRM_RESEND_COOLDOWN });
  ctx.waitUntil(countEvent(env, "signups"));
  return json(request, { success: true, message: "Check your inbox to confirm" });
}

async function handleTokenAction(request, url, env, ctx, action) {
  const email = (url.searchParams.get("email") || "").toLowerCase().trim();
  const city = (url.searchParams.get("city") || "").toLowerCase().trim();
  const token = url.searchParams.get("token") || "";

  if (!CITIES.includes(city) || !isValidEmail(email)) {
    return json(request, { error: "Invalid request", message: "Invalid link." }, 400);
  }

  let signedAction = action;
  if (action === "confirm") {
    const ts = Number(url.searchParams.get("ts"));
    const age = Math.floor(Date.now() / 1000) - ts;
    if (!Number.isInteger(ts) || age < 0 || age > CONFIRM_LINK_MAX_AGE) {
      return json(request, { error: "Expired", message: "This confirmation link has expired. Please sign up again." }, 403);
    }
    signedAction = `confirm|${ts}`;
  }

  if (!(await verifyToken(env, email, city, signedAction, token))) {
    return json(request, { error: "Invalid token", message: "This link is invalid or has been altered." }, 403);
  }

  const key = `${city}:${email}`;
  const alreadySubscribed = (await env.SUBSCRIBERS.get(key)) !== null;
  if (action === "confirm") {
    if (!alreadySubscribed) {
      await env.SUBSCRIBERS.put(key, "1");
      ctx.waitUntil(countEvent(env, "confirmations"));
    }
    return json(request, { success: true, message: "You're subscribed!" });
  }
  if (alreadySubscribed) ctx.waitUntil(countEvent(env, "unsubscribes"));
  await env.SUBSCRIBERS.delete(key);
  return json(request, { success: true, message: "You've been unsubscribed." });
}

function isAdmin(request, env) {
  const auth = request.headers.get("Authorization") || "";
  return Boolean(env.ADMIN_TOKEN) && timingSafeEqual(auth, `Bearer ${env.ADMIN_TOKEN}`);
}

async function loadSubscribers(env) {
  const subscribers = Object.fromEntries(CITIES.map(city => [city, []]));
  for (const city of CITIES) {
    let cursor;
    do {
      const page = await env.SUBSCRIBERS.list({ prefix: `${city}:`, cursor });
      for (const { name } of page.keys) subscribers[city].push(name.slice(city.length + 1));
      cursor = page.list_complete ? undefined : page.cursor;
    } while (cursor);
  }

  return subscribers;
}

async function handleListSubscribers(request, env) {
  if (!isAdmin(request, env)) return json(request, { error: "Unauthorized" }, 401);
  return json(request, await loadSubscribers(env));
}

async function handleStats(request, url, env) {
  if (!isAdmin(request, env)) return json(request, { error: "Unauthorized" }, 401);

  const days = Math.min(Math.max(Number(url.searchParams.get("days")) || 7, 1), 90);
  const daily = [];
  for (let i = days - 1; i >= 0; i--) {
    const date = sydneyDate(new Date(Date.now() - i * 24 * 60 * 60 * 1000));
    const row = { date };
    for (const event of STAT_EVENTS) {
      row[event] = Number(await env.SUBSCRIBERS.get(`stats:${date}:${event}`)) || 0;
    }
    daily.push(row);
  }

  const subscribers = await loadSubscribers(env);
  const subscribersByCity = Object.fromEntries(CITIES.map(city => [city, subscribers[city].length]));
  return json(request, { daily, subscribersByCity });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(request) });
    }

    try {
      const url = new URL(request.url);
      const action = url.searchParams.get("action");

      if (request.method === "POST") {
        // One-click unsubscribe from the List-Unsubscribe email header
        if (action === "unsubscribe") return await handleTokenAction(request, url, env, ctx, action);
        if (action === "view") {
          // Only count views from the real site, not arbitrary POSTs
          if (ALLOWED_ORIGINS.includes(request.headers.get("Origin"))) ctx.waitUntil(countEvent(env, "views"));
          return new Response(null, { status: 204, headers: corsHeaders(request) });
        }
        return await handleSignup(request, env, ctx);
      }

      if (request.method === "GET") {
        if (action === "confirm" || action === "unsubscribe") return await handleTokenAction(request, url, env, ctx, action);
        if (action === "subscribers") return await handleListSubscribers(request, env);
        if (action === "stats") return await handleStats(request, url, env);
      }

      return json(request, { error: "Method not allowed" }, 405);
    } catch (err) {
      return json(request, { error: "Server error" }, 500);
    }
  }
};
