/* Progressive enhancement: without JS, mobile navigation remains visible. */
(() => {
  'use strict';
  const trigger = document.getElementById('site-menu-toggle');
  const nav = document.getElementById('site-navigation');
  if (!trigger || !nav) return;
  document.documentElement.classList.add('has-nav-js');
  function setOpen(open) {
    nav.classList.toggle('is-open', open);
    trigger.setAttribute('aria-expanded', String(open));
    const glyph = trigger.querySelector('[data-menu-glyph]');
    if (glyph) glyph.textContent = open ? '×' : '☰';
  }
  trigger.addEventListener('click', () => {
    setOpen(trigger.getAttribute('aria-expanded') !== 'true');
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && trigger.getAttribute('aria-expanded') === 'true') {
      setOpen(false);
      trigger.focus();
    }
  });
  document.addEventListener('click', event => {
    if (trigger.getAttribute('aria-expanded') !== 'true') return;
    if (!nav.contains(event.target) && !trigger.contains(event.target)) setOpen(false);
  });
  nav.addEventListener('click', event => {
    if (event.target.closest('a') && window.matchMedia('(max-width: 768px)').matches) {
      setOpen(false);
    }
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 768 && trigger.getAttribute('aria-expanded') === 'true') {
      setOpen(false);
    }
  });
})();
