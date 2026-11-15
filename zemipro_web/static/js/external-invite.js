(() => {
  const button = document.querySelector('[data-copy-invite]');
  const input = document.querySelector('[data-invite-url]');
  if (!button || !input) return;
  button.addEventListener('click', async () => {
    const status = document.querySelector('[data-copy-status]');
    try {
      await navigator.clipboard.writeText(input.value);
      if (status) status.textContent = document.documentElement.lang === 'he'
        ? 'הקישור הועתק' : document.documentElement.lang === 'en'
          ? 'Link copied' : 'Ссылка скопирована';
    } catch (_error) {
      input.focus(); input.select();
      if (status) status.textContent = input.value;
    }
  });
})();
