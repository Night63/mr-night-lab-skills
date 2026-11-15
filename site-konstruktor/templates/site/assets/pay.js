/* Страница «Спасибо»: опрашивает GET {API}/order?inv=&t= каждые 3 с до 2 минут и показывает товар.
   После показа убирает InvId и токен из адресной строки (history.replaceState), чтобы они не утекли
   в историю, закладки и скриншоты. На странице должен быть <meta name="referrer" content="no-referrer">. */
(() => {
  const root = document.documentElement;
  const pay = document.querySelector('.pay[data-api]');
  if (!pay) return;
  const q = new URLSearchParams(location.search);
  const inv = q.get('InvId') || q.get('inv'), tok = q.get('Shp_token') || q.get('t');
  const show = (id) => ['pay-wait', 'pay-ok', 'pay-slow', 'pay-none'].forEach((x) => { document.getElementById(x).hidden = x !== id; });
  const ordEl = document.getElementById('pay-order');
  const clean = () => { try { history.replaceState(null, '', location.pathname); } catch (e) {} };
  if (!inv || !tok) { show('pay-none'); return; }
  const t0 = Date.now();
  const poll = async () => {
    try {
      const r = await fetch(pay.dataset.api + '/order?inv=' + encodeURIComponent(inv) + '&t=' + encodeURIComponent(tok), { cache: 'no-store' });
      const d = await r.json().catch(() => ({}));
      if (d.order) ordEl.textContent = (root.lang === 'en' ? 'Order ' : 'Заказ ') + d.order;
      if (d.status === 'paid' && d.key) {
        document.getElementById('pay-key').textContent = d.key;
        document.getElementById('pay-mail').textContent = root.lang === 'en' ? 'A copy has been sent to ' + d.email + '.' : 'Копия отправлена на ' + d.email + '.';
        show('pay-ok'); clean(); return;
      }
      if (r.status === 404) { show('pay-none'); clean(); return; }
    } catch (e) {}
    if (Date.now() - t0 < 120000) setTimeout(poll, 3000); else show('pay-slow');
  };
  poll();
  const cp = document.getElementById('pay-copy');
  if (cp) cp.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(document.getElementById('pay-key').textContent); } catch (e) {}
    const s = cp.querySelector(root.lang === 'en' ? '.en' : '.ru') || cp; const w = s.textContent;
    s.textContent = root.lang === 'en' ? 'Copied' : 'Скопировано'; setTimeout(() => { s.textContent = w; }, 2000);
  });
})();
