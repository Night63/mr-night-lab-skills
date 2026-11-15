/* Форма покупки: почта дважды + две отдельные галочки (оферта, согласие на ПД) → POST {API}/buy → переход на оплату.
   Живая оплата включается атрибутом data-pay="on" у формы — ТОЛЬКО после того, как в функции RK_TEST=0
   (см. scripts/_claude_pay.cmd). Без атрибута форма честно пишет, что оплата пока не подключена. */
(() => {
  const root = document.documentElement;
  const form = document.getElementById('buy');
  if (!form) return;
  const API = form.dataset.api;   // https://api.{{DOMAIN}}
  const SUPPORT = form.dataset.support || '';
  const e1 = form.querySelector('#buy-email'), e2 = form.querySelector('#buy-email2');
  const offer = form.querySelector('#buy-offer'), pd = form.querySelector('#buy-pd');
  const btn = form.querySelector('button[type=submit]'), hint = form.querySelector('#buy-match'), note = form.querySelector('.buy__note');
  const en = () => root.lang === 'en';
  const say = (ru, eng) => { note.textContent = en() ? eng : ru; };
  const check = () => {
    const ok1 = e1.validity.valid && e1.value.trim() !== '';
    const same = e1.value.trim().toLowerCase() === e2.value.trim().toLowerCase();
    hint.textContent = (e2.value && !same) ? (en() ? 'The emails do not match.' : 'Адреса почты не совпадают.') : '';
    btn.disabled = !(ok1 && same && offer.checked && pd.checked);
  };
  [e1, e2, offer, pd].forEach((el) => { el.addEventListener('input', check); el.addEventListener('change', check); });
  check();
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault(); check(); if (btn.disabled) return;
    if (form.dataset.pay !== 'on') { say('Оплата пока не подключена: она заработает после одобрения магазина платёжным сервисом.', 'Payment is not connected yet.'); return; }
    btn.disabled = true; say('Готовим оплату…', 'Preparing payment…');
    try {
      const r = await fetch(API + '/buy', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: e1.value.trim(), lang: en() ? 'en' : 'ru', offer: offer.checked, consent: pd.checked }) });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.pay_url) { location.href = d.pay_url; return; }
      if (d.error === 'email') say('Проверьте адрес почты.', 'Please check the email address.');
      else if (d.error === 'consent') say('Отметьте обе галочки.', 'Please tick both boxes.');
      else if (d.error === 'rate') say('Слишком много попыток. Попробуйте через час или напишите нам.', 'Too many attempts. Try again in an hour or write to us.');
      else if (d.error === 'closed') say('Продажи временно приостановлены.', 'Sales are paused for now.');
      else say('Не удалось начать оплату. Попробуйте ещё раз или напишите на ' + SUPPORT + '.', 'Could not start the payment. Try again or write to ' + SUPPORT + '.');
    } catch (e) { say('Нет связи с сервером оплаты. Проверьте интернет и попробуйте ещё раз.', 'Cannot reach the payment server.'); }
    check();
  });
})();
