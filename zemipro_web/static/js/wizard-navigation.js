/* Stage 08.4: warn before leaving an edited wizard step.
 * Never persist private form values in client-side storage. */
(() => {
  'use strict';
  const wizard = document.querySelector('.app-wizard');
  if (!wizard) return;
  const form = wizard.querySelector('.zw-panel > form');
  const back = wizard.querySelector('[data-wizard-back]');
  if (!form || !back) return;
  let dirty = false;
  form.addEventListener('input', () => { dirty = true; });
  form.addEventListener('change', () => { dirty = true; });
  back.addEventListener('click', event => {
    if (!dirty) return;
    if (!window.confirm(wizard.dataset.unsavedWarning || 'Leave without saving?')) {
      event.preventDefault();
      back.focus();
    }
  });
})();
