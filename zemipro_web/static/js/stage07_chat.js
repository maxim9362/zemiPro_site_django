/* Minimal polling: persisted source of truth, no user HTML injected. */
(() => {
  'use strict';
  const list = document.getElementById('chat-log');
  if (!list) return;
  let after = Number(list.dataset.lastId || '0');
  const me = Number(list.dataset.me || '0');
  const token = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
  const scroller = document.getElementById('chat-scroll');
  let running = false;

  async function readThrough(cursor) {
    if (!token || !cursor) return;
    try {
      await fetch(list.dataset.readUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: {'X-CSRFToken': token, 'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({through_id: String(cursor)}),
      });
    } catch (_) { /* A later request can retry. */ }
  }

  function appendMessage(item) {
    const li = document.createElement('li');
    li.dataset.messageId = String(item.id);
    li.style.cssText = 'padding:10px;border:1px solid #e2e8f0;border-radius:12px;overflow-wrap:anywhere';
    const stamp = document.createElement('small');
    stamp.textContent = new Date(item.created_at).toLocaleString();
    const body = document.createElement('p');
    body.dir = 'auto';
    body.style.whiteSpace = 'pre-wrap';
    body.textContent = item.body;
    li.append(stamp, body);
    list.append(li);
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
      let lastIncoming = 0;
      for (const item of payload.messages || []) {
        if (item.id <= after) continue;
        document.getElementById('chat-empty')?.remove();
        appendMessage(item);
        after = item.id;
        if (item.sender_id !== me) lastIncoming = item.id;
      }
      if (lastIncoming) await readThrough(lastIncoming);
      if (payload.messages?.length) scroller.scrollTop = scroller.scrollHeight;
    } catch (_) {
      // Connectivity faults never erase the stored conversation.
    } finally {
      running = false;
    }
  }

  window.addEventListener('online', () => { void poll(); });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) void poll();
  });
  window.setInterval(() => { void poll(); }, 6000);
  void poll();
})();
