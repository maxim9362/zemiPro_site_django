(() => {
  const button = document.querySelector('[data-copy-profile-link]');
  if (!button) return;
  button.addEventListener('click', async () => {
    const status = document.querySelector('[data-copy-status]');
    try {
      await navigator.clipboard.writeText(window.location.href);
      if (status) status.textContent = document.documentElement.lang === 'he'
        ? 'הקישור הועתק' : document.documentElement.lang === 'en'
          ? 'Link copied' : 'Ссылка скопирована';
    } catch (_error) {
      if (status) status.textContent = window.location.href;
    }
  });
})();
