// "Tell a mate" share row for moments people are happy with FillYaTank.
// Usage: <div class="share-row" data-share-ref="share-confirm"></div>
// Links go to the city page when ?city= is known, tagged with ?ref= for the stats email.
(function () {
    const CITY_NAMES = { sydney: 'Sydney', melbourne: 'Melbourne', brisbane: 'Brisbane', adelaide: 'Adelaide', perth: 'Perth' };

    document.querySelectorAll('.share-row').forEach(row => {
        const city = new URLSearchParams(location.search).get('city');
        const name = CITY_NAMES[city];
        const url = `https://fillyatank.app/${name ? city : ''}?ref=${row.dataset.shareRef}`;
        const text = name
            ? `I get one free email when ${name} petrol hits the bottom of the price cycle. No ads, no app:`
            : 'I get one free email when petrol hits the bottom of the price cycle. No ads, no app:';

        const link = (label, href) => {
            const a = document.createElement('a');
            a.className = 'share-btn';
            a.href = href;
            a.target = '_blank';
            a.rel = 'noopener';
            a.textContent = label;
            return a;
        };

        if (navigator.share) {
            const native = document.createElement('button');
            native.type = 'button';
            native.className = 'share-btn share-btn-primary';
            native.textContent = 'Share';
            native.addEventListener('click', () => navigator.share({ title: 'FillYaTank', text, url }).catch(() => {}));
            row.appendChild(native);
        }
        row.appendChild(link('WhatsApp', `https://wa.me/?text=${encodeURIComponent(text + ' ' + url)}`));
        row.appendChild(link('Facebook', `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`));

        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'share-btn';
        copy.textContent = 'Copy link';
        copy.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(url);
                copy.textContent = 'Copied!';
            } catch (e) {
                copy.textContent = url;
            }
        });
        row.appendChild(copy);
    });
})();
