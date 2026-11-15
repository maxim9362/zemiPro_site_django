/* Stage 08.5 — accessible private chat polling.
 * Server remains authoritative: polling only renders escaped text and
 * registered forms whose POST handlers re-check permissions/CSRF/consent.
 * Do not insert user content with innerHTML. No browser storage. */
(() => {
  'use strict';
  const list = document.getElementById('chat-log');
  if (!list || list.dataset.history === '1') return;
  const scroller = document.getElementById('chat-scroll');
  const status = document.getElementById('chat-poll-status');
  const me = Number(list.dataset.me || '0');
  const token = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
  const templateId = '999999999';
  let after = Number(list.dataset.lastId || '0');
  let running = false;

  function isId(value) {
    return Number.isSafeInteger(value) && value > 0;
  }

  function setStatus(label) {
    if (status) status.textContent = label || '';
  }

  async function readThrough(cursor) {
    if (!token || !isId(cursor)) return;
    try {
      await fetch(list.dataset.readUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: {
          'X-CSRFToken': token,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({through_id: String(cursor)}),
      });
    } catch (_) {
      /* A later request can retry; never invent a read receipt. */
    }
  }

  function applyMessageActions(li, item) {
    const own = Number(item.sender_id) === me && list.dataset.canSend === '1';
    const template = document.getElementById(
      own ? 'chat-actions-sender' : 'chat-actions-receiver'
    );
    if (!template) return;
    const fragment = template.content.cloneNode(true);
    /* Only numeric server-issued message IDs can fill this server-generated
       URL prototype; JS never constructs actions from user message bodies. */
    const id = Number(item.id);
    if (!isId(id)) return;
    fragment.querySelectorAll('[action], [href], [id], [for]').forEach(element => {
      ['action', 'href', 'id', 'for'].forEach(attribute => {
        const value = element.getAttribute(attribute);
        if (value && value.includes(templateId)) {
          element.setAttribute(attribute, value.replace(templateId, String(id)));
        }
      });
    });
    li.append(fragment);
  }

  function appendMessage(item) {
    const id = Number(item.id);
    if (!isId(id) || list.querySelector('[data-message-id="' + id + '"]')) return false;
    const li = document.createElement('li');
    li.classList.add('comm-message');
    if (Number(item.sender_id) === me) li.classList.add('comm-message--mine');
    li.dataset.messageId = String(id);

    const stamp = document.createElement('small');
    stamp.className = 'comm-message__meta';
    const when = document.createElement('bdi');
    when.dir = 'ltr';
    const date = new Date(item.created_at);
    when.textContent = Number.isNaN(date.valueOf()) ? ''
      : date.toLocaleString(document.documentElement.lang || 'ru');
    const state = document.createElement('span');
    state.dataset.readState = '';
    state.textContent = item.read ? list.dataset.readLabel : list.dataset.deliveredLabel;
    stamp.append(when, document.createTextNode(' · '), state);

    const body = document.createElement('p');
    body.dir = 'auto';
    body.className = 'comm-message__body';
    body.textContent = String(item.body || '');

    const attachments = document.createElement('div');
    attachments.className = 'comm-message__attachments';
    li.append(stamp, body, attachments);
    applyMessageActions(li, item);
    list.append(li);
    return true;
  }

  function appendAttachment(attachment) {
    const messageId = Number(attachment.message_id);
    const imageId = Number(attachment.id);
    if (!isId(messageId) || !isId(imageId)) return;
    const row = list.querySelector('[data-message-id="' + messageId + '"]');
    if (!row || row.querySelector('[data-attachment-id="' + imageId + '"]')) return;
    const container = row.querySelector('.comm-message__attachments');
    if (!container) return;
    let url;
    try {
      url = new URL(attachment.url, window.location.origin);
    } catch (_) { return; }
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/chat/')) {
      return;
    }
    const link = document.createElement('a');
    link.dataset.attachmentId = String(imageId);
    link.href = url.pathname + url.search;
    const picture = document.createElement('img');
    picture.src = link.href;
    picture.alt = list.dataset.filesLabel;
    picture.width = 160;
    picture.height = 120;
    picture.loading = 'lazy';
    link.append(picture);
    container.append(link);
  }

  async function poll() {
    if (running || document.hidden || !navigator.onLine) return;
    running = true;
    try {
      const response = await fetch(list.dataset.pollUrl + '?after=' + after, {
        credentials: 'same-origin', cache: 'no-store',
      });
      if (!response.ok) return;
      const payload = await response.json();
      const nearBottom = scroller && (
        scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 150
      );
      for (const value of payload.read_ids || []) {
        const id = Number(value);
        if (!isId(id)) continue;
        const state = list.querySelector('[data-message-id="' + id + '"] [data-read-state]');
        if (state) state.textContent = list.dataset.readLabel;
      }
      let lastIncoming = 0;
      let newMessages = 0;
      for (const item of payload.messages || []) {
        const id = Number(item.id);
        if (!isId(id) || id <= after) continue;
        if (!appendMessage(item)) continue;
        document.getElementById('chat-empty')?.remove();
        after = id;
        newMessages++;
        if (Number(item.sender_id) !== me) lastIncoming = id;
      }
      for (const attachment of payload.attachments || []) appendAttachment(attachment);
      if (lastIncoming || after) await readThrough(lastIncoming || after);
      if (newMessages && nearBottom && scroller) scroller.scrollTop = scroller.scrollHeight;
      setStatus('');
    } catch (_) {
      /* Connectivity/server failures never clear persisted history. */
    } finally {
      running = false;
    }
  }

  window.addEventListener('offline', () => setStatus(status?.dataset.offlineLabel));
  window.addEventListener('online', () => {
    setStatus(status?.dataset.onlineLabel);
    void poll();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) void poll();
  });
  if (!navigator.onLine) setStatus(status?.dataset.offlineLabel);
  window.setInterval(() => { void poll(); }, 6000);
  void readThrough(after);
  void poll();
})();
