// FillYaTank site script: live status, signup form, small delights, anonymous view count.
// Shared by the homepage and the city pages.

const CITY_NAMES = { sydney: 'Sydney', melbourne: 'Melbourne', brisbane: 'Brisbane', adelaide: 'Adelaide', perth: 'Perth' };

async function fetchText(url) {
    try {
        const response = await fetch(url, { cache: 'no-store' });
        return response.ok ? await response.text() : null;
    } catch (e) {
        return null;
    }
}

function isoDate(date, timeZone) {
    return date.toLocaleDateString('en-CA', { timeZone }); // YYYY-MM-DD
}

async function updateStatus() {
    const [stateText, lastRun, tipsText, perthText] = await Promise.all([
        fetchText('/data/state.json'),
        fetchText('/data/last_run.txt'),
        fetchText('/data/tips.json'),
        fetchText('/data/perth_alert.json')
    ]);
    const parse = text => { try { return JSON.parse(text); } catch (e) { return null; } };
    const state = parse(stateText) || {};
    const tips = parse(tipsText) || {};
    const perthAlert = parse(perthText) || {};

    // Perth alerts come from FuelWatch's next-day prices: green on the day before a jump
    const perthToday = isoDate(new Date(), 'Australia/Perth');
    const perthTomorrow = new Date(perthToday + 'T12:00:00Z');
    perthTomorrow.setUTCDate(perthTomorrow.getUTCDate() + 1);
    const perthJumpTomorrow = perthAlert.last_alert_for === perthTomorrow.toISOString().slice(0, 10);

    const buyCities = [];
    document.querySelectorAll('.pill[data-city]').forEach(pill => {
        const city = pill.dataset.city;
        const note = document.querySelector(`.city-note[data-note="${city}"]`);
        let phase = state[city];
        let noteText = tips[city] || '';
        let label = 'Fill up now';
        if (city === 'perth' && perthJumpTomorrow) {
            phase = 'BUY';
            label = 'Fill up today';
            noteText = 'Prices jump tomorrow (FuelWatch)';
        }
        pill.classList.remove('buy', 'wait');
        if (phase === 'BUY') {
            pill.classList.add('buy');
            pill.textContent = label;
            buyCities.push(city);
        } else if (phase === 'WAIT') {
            pill.classList.add('wait');
            pill.textContent = 'Hold off';
        } else {
            pill.textContent = 'Unavailable';
        }
        if (note) note.textContent = noteText;
    });

    const lastChecked = document.getElementById('lastChecked');
    const date = lastRun && new Date(lastRun.trim() + 'T00:00:00');
    if (lastChecked && date && !isNaN(date)) {
        lastChecked.textContent = 'Last checked ' + date.toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });
    }

    if (buyCities.length) {
        const names = buyCities.map(c => CITY_NAMES[c]);
        const list = names.length === 1 ? names[0] : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
        const text = buyCities.length === 1 && buyCities[0] === 'perth' && perthJumpTomorrow
            ? 'Perth prices jump tomorrow. Fill up today!'
            : `${list} ${names.length === 1 ? 'is' : 'are'} at the bottom of the price cycle. Time to fill ya tank!`;
        const banner = document.getElementById('buyBanner');
        if (banner) {
            document.getElementById('buyBannerText').textContent = text;
            banner.classList.remove('hidden');
        }
    }
}

document.getElementById('backToSignup')?.addEventListener('click', event => {
    event.preventDefault();
    document.getElementById('signupForm').scrollIntoView({ behavior: 'smooth', block: 'center' });
    document.getElementById('email').focus({ preventScroll: true });
});

document.getElementById('signupForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const button = document.getElementById('submitBtn');
    const message = document.getElementById('formMessage');
    const buttonText = button.textContent;

    const show = (kind, text) => {
        message.className = 'form-message ' + kind;
        message.textContent = text;
    };

    // Honeypot filled: quietly pretend it worked
    if (form.website.value) {
        show('success', 'Check your inbox to confirm.');
        return;
    }

    if (!form.email.value.trim() || !form.city.value) {
        show('error', 'Please enter your email and choose your city.');
        return;
    }

    button.disabled = true;
    button.textContent = 'Sending…';
    show('', '');

    try {
        const response = await fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'Accept': 'application/json' }
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.alreadySent) {
            show('success', data.message);
        } else if (response.ok) {
            const city = CITY_NAMES[form.city.value];
            show('success', `Nearly done! Check your inbox and click the link to confirm your ${city} alerts.`);
            celebrate(button);
            form.reset();
        } else {
            show('error', data.error || 'Something went wrong. Please try again.');
        }
    } catch (err) {
        show('error', "Couldn't reach the server. Please check your connection and try again.");
    } finally {
        button.disabled = false;
        button.textContent = buttonText;
    }
});

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function celebrate(origin) {
    if (reduceMotion || typeof confetti !== 'function') return;
    const rect = origin.getBoundingClientRect();
    const shoot = confetti.create(null, { resize: true, useWorker: false });
    shoot({
        particleCount: 90,
        spread: 70,
        startVelocity: 38,
        origin: { x: (rect.left + rect.width / 2) / innerWidth, y: rect.top / innerHeight },
        colors: ['#1e7d46', '#7ac68e', '#ffd84d', '#1b1f1d']
    });
}

// Hand-drawn annotations
if (window.RoughNotation) {
    const { annotate } = RoughNotation;
    const underline = document.querySelector('.mark-underline');
    if (underline) {
        const draw = () => annotate(underline, { type: 'underline', color: '#1e7d46', strokeWidth: 4, padding: 2, iterations: 2, animate: !reduceMotion, animationDuration: 900 }).show();
        (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(draw);
    }
}

updateStatus();

// Anonymous view count: no cookies, no identifiers
const ref = (new URLSearchParams(location.search).get('ref') || '').toLowerCase();
navigator.sendBeacon('https://api.fillyatank.app/?action=view' + (/^[a-z0-9-]{1,24}$/.test(ref) ? '&ref=' + ref : ''));
