/* Small dependency-free browser demo. Access token lives in sessionStorage for
   local testing. Use HttpOnly secure cookies and CSRF protection in production. */
const $ = (id) => document.getElementById(id);
const state = {
  token: sessionStorage.getItem('ping_token'), me: null, users: [], onlineIds: new Set(),
  conversations: [], current: null, ws: null, nextOffset: null, loadedIds: new Set(),
};
const API = '/api/v1';

function showNotice(message) {
  const notice = $('notice'); notice.textContent = String(message); notice.hidden = false;
  clearTimeout(showNotice.timer); showNotice.timer = setTimeout(() => { notice.hidden = true; }, 5000);
}
function formatError(error) { return typeof error === 'string' ? error : String(error?.message || error); }
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const res = await fetch(API + path, { ...options, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { const body = await res.json(); detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}
function button(text, action, className = '') {
  const element = document.createElement('button'); element.type = 'button'; element.textContent = text;
  element.className = className; element.addEventListener('click', action); return element;
}
function setSignedIn(signedIn) {
  $('auth-panel').hidden = signedIn; $('app-panel').hidden = !signedIn;
  $('connection-status').textContent = signedIn ? 'Connecting...' : 'Offline';
}
async function login(username, password) {
  const response = await api('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
  state.token = response.access_token; sessionStorage.setItem('ping_token', state.token);
  await boot();
}
async function boot() {
  try {
    state.me = await api('/auth/me'); setSignedIn(true);
    $('my-name').textContent = state.me.display_name;
    $('my-handle').textContent = `@${state.me.username}`;
    $('bio-input').value = state.me.bio;
    await Promise.all([refreshUsers(), refreshConversations(), refreshStatuses()]);
    connectWebSocket();
  } catch (error) { logout(); showNotice(formatError(error)); }
}
function logout() {
  state.token = null; state.me = null; state.current = null;
  state.onlineIds = new Set(); state.loadedIds.clear();
  sessionStorage.removeItem('ping_token');
  if (state.ws) { const socket = state.ws; state.ws = null; socket.close(); }
  setSignedIn(false);
}
async function refreshUsers() {
  const [users, online] = await Promise.all([api('/users'), api('/users/online')]);
  state.users = users; state.onlineIds = new Set(online.users.map((u) => u.id));
  $('online-count').textContent = online.count;
  const onlineContainer = $('online-users'); onlineContainer.replaceChildren();
  if (!online.users.length) { const empty = document.createElement('p'); empty.className = 'small muted'; empty.textContent = 'Nobody online yet.'; onlineContainer.append(empty); }
  for (const user of online.users) {
    if (user.id !== state.me.id) onlineContainer.append(buddyElement(user, true));
  }
  const allContainer = $('users'); allContainer.replaceChildren();
  state.users.forEach((user) => allContainer.append(buddyElement(user, state.onlineIds.has(user.id))));
}
function buddyElement(user, online) {
  const item = button('', () => openConversation(user.id)); item.className = 'buddy';
  const avatar = document.createElement('span'); avatar.className = 'mini-avatar'; avatar.textContent = '☺';
  const names = document.createElement('span'); names.className = 'buddy-info';
  const name = document.createElement('span'); name.textContent = user.display_name;
  const subtitle = document.createElement('small'); subtitle.textContent = user.bio || `@${user.username}`;
  names.append(name, subtitle);
  const dot = document.createElement('span'); dot.className = 'presence' + (online ? ' live' : '');
  item.append(avatar, names, dot); return item;
}
async function refreshConversations() {
  state.conversations = await api('/conversations');
  const root = $('conversations'); root.replaceChildren();
  if (!state.conversations.length) {
    const empty = document.createElement('p'); empty.className = 'small muted'; empty.textContent = 'No chats yet.'; root.append(empty);
  }
  for (const conversation of state.conversations) {
    const item = buddyElement(conversation.other_user, state.onlineIds.has(conversation.other_user.id));
    const subtitle = item.querySelector('small');
    subtitle.textContent = conversation.status ? `↳ ${conversation.status.text}` : 'Direct message';
    item.classList.toggle('active', state.current?.id === conversation.id);
    // Clone strips the buddy's default click handler, then bind this exact thread.
    const threadButton = item.cloneNode(true);
    threadButton.addEventListener('click', () => selectConversation(conversation));
    root.append(threadButton);
  }
}
async function refreshStatuses() {
  const statuses = await api('/statuses?limit=30');
  const root = $('statuses'); root.replaceChildren();
  for (const status of statuses) {
    const author = status.author_id === state.me.id ? state.me : state.users.find((u) => u.id === status.author_id);
    const row = document.createElement('div'); row.className = 'status-item';
    const name = document.createElement('h3'); name.textContent = `${author?.display_name || 'User'} · ${new Date(status.created_at).toLocaleDateString()}`;
    const text = document.createElement('p'); text.textContent = status.text;
    row.append(name, text);
    if (status.author_id !== state.me.id) {
      row.append(button('↳ Reply in a private thread', () => openConversation(status.author_id, status.id)));
    }
    root.append(row);
  }
}
async function openConversation(recipientId, statusId = null) {
  try {
    const conversation = await api('/conversations', {
      method: 'POST', body: JSON.stringify({ recipient_id: recipientId, status_id: statusId }),
    });
    await refreshConversations(); await selectConversation(conversation);
  } catch (error) { showNotice(formatError(error)); }
}
async function selectConversation(conversation) {
  try {
    state.current = conversation; state.loadedIds.clear(); state.nextOffset = null;
    $('chat-placeholder').hidden = true; $('chat-active').hidden = false;
    $('chat-title').textContent = `💬 ${conversation.other_user.display_name}`;
    $('chat-context').hidden = !conversation.status;
    $('chat-context').textContent = conversation.status ? `📌 Replying to status: “${conversation.status.text}”` : '';
    $('messages').replaceChildren();
    await loadHistory(false); await refreshConversations();
  } catch (error) { showNotice(formatError(error)); }
}
async function loadHistory(older) {
  if (!state.current) return;
  const convId = state.current.id;
  const offset = older ? state.nextOffset : 0;
  if (offset === null) return;
  const page = await api(`/conversations/${convId}/messages?limit=20&offset=${offset}`);
  if (state.current?.id !== convId) return;
  const scrollArea = $('messages'); const oldHeight = scrollArea.scrollHeight;
  for (const message of page.items) addMessage(message, true);
  state.nextOffset = page.next_offset;
  $('load-older').hidden = !page.has_more;
  if (older) scrollArea.scrollTop += scrollArea.scrollHeight - oldHeight;
  else scrollArea.scrollTop = scrollArea.scrollHeight;
}
function addMessage(message, prepend = false) {
  if (state.loadedIds.has(message.id) || message.conversation_id !== state.current?.id) return;
  state.loadedIds.add(message.id);
  const box = document.createElement('article'); box.className = 'message' + (message.sender_id === state.me.id ? ' mine' : '');
  box.dataset.messageId = message.id;
  const meta = document.createElement('div'); meta.className = 'meta';
  meta.textContent = `${message.sender_id === state.me.id ? 'You' : state.current.other_user.display_name} · ${new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  if (message.text) { const content = document.createElement('div'); content.textContent = message.text; bubble.append(content); }
  if (message.attachments.length) {
    const media = document.createElement('div'); media.className = 'media';
    for (const item of message.attachments) {
      const placeholder = document.createElement('span'); placeholder.textContent = `Loading ${item.original_name}...`;
      media.append(placeholder); renderMedia(item, placeholder);
    }
    bubble.append(media);
  }
  box.append(meta, bubble);
  if (prepend) $('messages').prepend(box); else $('messages').append(box);
}
async function renderMedia(item, placeholder) {
  try {
    const response = await fetch(item.url, { headers: { Authorization: `Bearer ${state.token}` } });
    if (!response.ok) throw new Error('Could not load media');
    const objectUrl = URL.createObjectURL(await response.blob());
    const element = document.createElement(item.content_type.startsWith('video/') ? 'video' : 'img');
    element.src = objectUrl; element.alt = item.original_name;
    if (element.tagName === 'VIDEO') element.controls = true;
    element.addEventListener('error', () => URL.revokeObjectURL(objectUrl), { once: true });
    placeholder.replaceWith(element);
  } catch (error) { placeholder.textContent = `Attachment unavailable: ${item.original_name}`; }
}
function connectWebSocket() {
  if (!state.token) return;
  if (state.ws) state.ws.close();
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}${API}/ws?token=${encodeURIComponent(state.token)}`);
  state.ws = ws;
  ws.addEventListener('open', () => { $('connection-status').textContent = '🟢 Live connection'; });
  ws.addEventListener('message', async (event) => {
    try {
      const packet = JSON.parse(event.data);
      if (packet.type === 'presence.update') { await refreshUsers(); await refreshConversations(); }
      if (packet.type === 'message.new') {
        if (packet.message.conversation_id === state.current?.id) {
          const scrollArea = $('messages'); const nearBottom = scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < 100;
          addMessage(packet.message);
          if (state.nextOffset !== null) state.nextOffset += 1; // Offset shifts as new messages arrive.
          if (nearBottom || packet.message.sender_id === state.me.id) scrollArea.scrollTop = scrollArea.scrollHeight;
        }
        await refreshConversations();
      }
      if (packet.type === 'message.error') showNotice(packet.detail);
    } catch (error) { showNotice(formatError(error)); }
  });
  ws.addEventListener('close', () => {
    if (state.ws !== ws) return;
    state.ws = null; $('connection-status').textContent = 'Disconnected — reconnecting...';
    if (state.token) setTimeout(() => { if (state.token && !state.ws) connectWebSocket(); }, 3000);
  });
  ws.addEventListener('error', () => { $('connection-status').textContent = 'Connection issue'; });
}
async function sendMessage(event) {
  event.preventDefault(); if (!state.current) return;
  const input = $('message-text'); const fileInput = $('message-files');
  const text = input.value; const files = [...fileInput.files];
  if (!text.trim() && files.length === 0) return;
  if (files.length > 4) { showNotice('Choose up to four attachments per message.'); return; }
  const convId = state.current.id;
  $('send-button').disabled = true;
  try {
    const attachmentIds = [];
    for (const file of files) {
      const form = new FormData(); form.append('file', file);
      const attachment = await api(`/conversations/${convId}/attachments`, { method: 'POST', body: form });
      attachmentIds.push(attachment.id);
    }
    const payload = { text, attachment_ids: attachmentIds };
    if (state.ws?.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: 'message.send', conversation_id: convId, ...payload }));
    } else {
      const message = await api(`/conversations/${convId}/messages`, { method: 'POST', body: JSON.stringify(payload) });
      addMessage(message); $('messages').scrollTop = $('messages').scrollHeight;
    }
    input.value = ''; fileInput.value = ''; $('file-count').textContent = '';
  } catch (error) { showNotice(formatError(error)); }
  finally { $('send-button').disabled = false; input.focus(); }
}

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const data = new FormData(event.target);
  try { await login(data.get('username'), data.get('password')); }
  catch (error) { showNotice(formatError(error)); }
});
$('register-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const data = Object.fromEntries(new FormData(event.target));
  try { await api('/auth/register', { method: 'POST', body: JSON.stringify(data) }); await login(data.username, data.password); }
  catch (error) { showNotice(formatError(error)); }
});
$('logout').addEventListener('click', logout);
$('save-bio').addEventListener('click', async () => {
  try { state.me = await api('/users/me', { method: 'PATCH', body: JSON.stringify({ bio: $('bio-input').value }) }); showNotice('Bio saved!'); }
  catch (error) { showNotice(formatError(error)); }
});
$('status-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await api('/statuses', { method: 'POST', body: JSON.stringify({ text: $('status-text').value }) }); $('status-text').value = ''; await refreshStatuses(); }
  catch (error) { showNotice(formatError(error)); }
});
$('load-older').addEventListener('click', () => loadHistory(true).catch((error) => showNotice(formatError(error))));
$('send-form').addEventListener('submit', sendMessage);
$('message-text').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('send-form').requestSubmit(); }
});
$('message-files').addEventListener('change', () => { $('file-count').textContent = `${$('message-files').files.length} selected`; });

/* ---------- Search by status keywords ---------- */
async function searchUsers(query) {
  if (!query.trim()) {
    $('search-results-section').hidden = true;
    return;
  }
  try {
    const encoded = encodeURIComponent(query.trim());
    const data = await api(`/users/search?q=${encoded}`);
    const root = $('search-results');
    root.replaceChildren();
    $('search-count').textContent = data.count;
    if (!data.results.length) {
      const empty = document.createElement('p');
      empty.className = 'small muted';
      empty.textContent = 'No matching statuses found.';
      root.append(empty);
    }
    for (const item of data.results) {
      const el = document.createElement('div');
      el.className = 'search-item';
      const name = document.createElement('strong');
      name.textContent = item.is_friend ? `★ ${item.display_name}` : item.display_name;
      const status = document.createElement('p');
      status.textContent = item.matching_status;
      const subtitle = document.createElement('small');
      subtitle.textContent = `@${item.username}${item.is_friend ? ' (friend)' : ''}`;
      el.append(name, subtitle, status);
      el.addEventListener('click', () => openConversation(item.id));
      root.append(el);
    }
    $('search-results-section').hidden = false;
  } catch (error) {
    showNotice(formatError(error));
  }
}

$('search-button').addEventListener('click', () => searchUsers($('search-input').value));
$('search-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    searchUsers($('search-input').value);
  }
});

if (state.token) boot();
