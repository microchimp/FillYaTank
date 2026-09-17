/**
 * FillYaTank Signup Worker
 *
 * POST /                                   signup form -> sends confirmation email
 * GET  /?action=confirm&email&city&token   adds subscriber
 * GET  /?action=unsubscribe&email&city&token removes subscriber
 * GET  /?action=subscribers (Bearer ADMIN_TOKEN) -> {city: [emails]} for main.py
 */

const CITIES = ["sydney", "melbourne", "brisbane", "adelaide", "perth"];

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

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
  };
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(), "Content-Type": "application/json" }
  });
}

async function sendConfirmationEmail(env, email, city) {
  const token = await generateToken(env.SECRET_KEY, email, city, "confirm");
  const confirmUrl = `${env.SITE_URL}/confirm.html?email=${encodeURIComponent(email)}&city=${city}&token=${token}`;
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
    You'll only hear from us when prices hit bottom. That's it.
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

async function handleSignup(request, env) {
  const formData = await request.formData();
  const email = (formData.get("email") || "").toLowerCase().trim();
  const city = (formData.get("city") || "").toLowerCase().trim();
  const honeypot = formData.get("website") || "";

  // Silently reject bots but return success
  if (honeypot) return json({ success: true });

  if (!email || !isValidEmail(email)) return json({ error: "Invalid email address" }, 400);
  if (!city || !CITIES.includes(city)) return json({ error: "Invalid city" }, 400);

  const sent = await sendConfirmationEmail(env, email, city);
  return sent
    ? json({ success: true, message: "Check your inbox to confirm" })
    : json({ error: "Failed to send email" }, 500);
}

async function handleTokenAction(url, env, action) {
  const email = (url.searchParams.get("email") || "").toLowerCase().trim();
  const city = (url.searchParams.get("city") || "").toLowerCase().trim();
  const token = url.searchParams.get("token") || "";

  if (!CITIES.includes(city) || !isValidEmail(email)) {
    return json({ error: "Invalid request", message: "Invalid link." }, 400);
  }
  if (!(await verifyToken(env, email, city, action, token))) {
    return json({ error: "Invalid token", message: "This link is invalid or has been altered." }, 403);
  }

  const key = `${city}:${email}`;
  if (action === "confirm") {
    await env.SUBSCRIBERS.put(key, new Date().toISOString().slice(0, 10));
    return json({ success: true, message: "You're subscribed!" });
  }
  await env.SUBSCRIBERS.delete(key);
  return json({ success: true, message: "You've been unsubscribed." });
}

async function handleListSubscribers(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (!env.ADMIN_TOKEN || !timingSafeEqual(auth, `Bearer ${env.ADMIN_TOKEN}`)) {
    return json({ error: "Unauthorized" }, 401);
  }

  const subscribers = Object.fromEntries(CITIES.map(city => [city, []]));
  let cursor;
  do {
    const page = await env.SUBSCRIBERS.list({ cursor });
    for (const { name } of page.keys) {
      const [city, ...rest] = name.split(":");
      if (subscribers[city]) subscribers[city].push(rest.join(":"));
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  return json(subscribers);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }

    try {
      if (request.method === "POST") return await handleSignup(request, env);

      if (request.method === "GET") {
        const url = new URL(request.url);
        const action = url.searchParams.get("action");
        if (action === "confirm" || action === "unsubscribe") return await handleTokenAction(url, env, action);
        if (action === "subscribers") return await handleListSubscribers(request, env);
      }

      return json({ error: "Method not allowed" }, 405);
    } catch (err) {
      return json({ error: "Server error" }, 500);
    }
  }
};
