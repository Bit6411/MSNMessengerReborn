/* Small dependency-free browser demo. Access token lives in sessionStorage for
   local testing. Use HttpOnly secure cookies and CSRF protection in production. */
const $ = (id) => document.getElementById(id);
const state = {
  token: sessionStorage.getItem('ping_token'), me: null, onlineAvailability: new Map(),
  conversations: [], current: null, ws: null, nextOffset: null, loadedIds: new Set(), mediaUrls: new Set(),
};
const API = '/api/v1';
const statusLabels = { online: 'Online', idle: 'Idle', dnd: 'Do Not Disturb', offline: 'Offline' };
const statusClasses = { online: 'live', idle: 'idle', dnd: 'dnd' };
const buddyStatus = $('buddy-status');
let statusAnchor = null;
let statusCloseTimer;
let searchRequest = 0;

function hideBuddyStatus() {
  clearTimeout(statusCloseTimer);
  statusAnchor?.removeAttribute('aria-describedby');
  statusAnchor = null;
  buddyStatus.hidden = true;
}

function positionBuddyStatus() {
  if (!statusAnchor) return;
  const row = statusAnchor.getBoundingClientRect();
  const sidebar = statusAnchor.closest('.orbital-ring').getBoundingClientRect();
  if (row.bottom <= Math.max(sidebar.top, 0) || row.top >= Math.min(sidebar.bottom, window.innerHeight)) {
    hideBuddyStatus();
    return;
  }
  const { offsetWidth: width, offsetHeight: height } = buddyStatus;
  const fitsBeside = row.right + 6 + width <= window.innerWidth - 8;
  const below = row.bottom + height + 6 <= window.innerHeight - 8;
  const left = fitsBeside ? row.right + 6 : Math.min(row.left, window.innerWidth - width - 8);
  const top = fitsBeside ? row.top : below ? row.bottom + 6 : row.top - height - 6;
  buddyStatus.style.left = `${Math.max(8, left)}px`;
  buddyStatus.style.top = `${Math.max(8, Math.min(top, window.innerHeight - height - 8))}px`;
}

function showBuddyStatus(anchor, user) {
  hideBuddyStatus();
  const availability = state.onlineAvailability.get(user.id) || 'offline';
  const description = user.current_status?.description || '';
  // Use latest_status_post for the status text (separate from availability status)
  const statusPost = user.latest_status_post;
  const statusText = statusPost?.text || '';
  $('buddy-status-name').textContent = user.display_name;
  $('buddy-status-dot').className = `presence ${statusClasses[availability] || ''}`;
  $('buddy-status-label').textContent = statusLabels[availability];
  $('buddy-status-description').textContent = description || statusText;
  $('buddy-status-description').hidden = !description && !statusText;
  // Show "Reply to status" only if the user has a status post
  $('buddy-reply-status').hidden = !statusText;
  // Store user data for button handlers
  buddyStatus.dataset.userId = user.id;
  buddyStatus.dataset.statusId = statusPost?.id || '';
  statusAnchor = anchor;
  buddyStatus.hidden = false;
  anchor.setAttribute('aria-describedby', buddyStatus.id);
  positionBuddyStatus();
}

function scheduleBuddyStatusClose() {
  clearTimeout(statusCloseTimer);
  statusCloseTimer = setTimeout(() => {
    if (!statusAnchor?.matches(':focus-visible, :hover') && !buddyStatus.matches(':hover')) hideBuddyStatus();
  }, 160);
}

buddyStatus.addEventListener('pointerenter', () => clearTimeout(statusCloseTimer));
buddyStatus.addEventListener('pointerleave', scheduleBuddyStatusClose);
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') hideBuddyStatus();
});
window.addEventListener('resize', positionBuddyStatus);
window.addEventListener('scroll', positionBuddyStatus, true);

function renderMyStatus({ availability, description }) {
  $('my-status-dot').className = `presence ${statusClasses[availability]}`;
  $('my-status-label').textContent = statusLabels[availability];
  $('status-form').elements.availability.value = availability;
  $('status-description').value = description;
  $('my-status-description').textContent = description;
  $('my-status-description').hidden = !description;
}

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
    try {
      const body = await res.json();
      if (body.detail != null) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw Object.assign(new Error(detail), { status: res.status });
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
  const token = state.token;
  try {
    const [me, status] = await Promise.all([api('/auth/me'), api('/users/me/status')]);
    if (state.token !== token) return;
    state.me = me;
    renderMyStatus(status);
    $('status-editor').open = false;
    setSignedIn(true);
    $('my-name').textContent = state.me.display_name;
    $('my-handle').textContent = `@${state.me.username}`;
    $('bio-input').value = state.me.bio;
    await refreshUsers();
    await refreshConversations();
    if (state.token === token) connectWebSocket();
  } catch (error) {
    if (state.token !== token) return;
    logout();
    showNotice(formatError(error));
  }
}
function clearChat() {
  state.current = null;
  state.loadedIds.clear();
  state.nextOffset = null;
  $('chat-active').hidden = true;
  $('chat-placeholder').hidden = false;
  $('messages').replaceChildren();
  for (const url of state.mediaUrls) URL.revokeObjectURL(url);
  state.mediaUrls.clear();
  $('send-form').reset();
  $('file-count').textContent = '';
}
function logout() {
  hideBuddyStatus();
  state.token = null; state.me = null;
  state.onlineAvailability.clear();
  state.conversations = [];
  clearChat();
  searchRequest += 1;
  $('search-input').value = '';
  $('search-results').replaceChildren();
  $('search-results-section').hidden = true;
  sessionStorage.removeItem('ping_token');
  if (state.ws) { const socket = state.ws; state.ws = null; socket.close(); }
  setSignedIn(false);
}
async function refreshUsers() {
  const token = state.token;
  const [users, online] = await Promise.all([api('/users'), api('/users/online')]);
  if (state.token !== token) return;
  state.onlineAvailability = new Map(online.users.map((user) => [user.id, user.availability]));
  $('online-count').textContent = online.count;
  const onlineContainer = $('online-users'); onlineContainer.replaceChildren();
  if (!online.users.length) { const empty = document.createElement('p'); empty.className = 'small muted'; empty.textContent = 'Nobody online yet.'; onlineContainer.append(empty); }
  for (const user of online.users) {
    if (user.id !== state.me.id) onlineContainer.append(buddyElement(user));
  }
  const allContainer = $('users'); allContainer.replaceChildren();
  users.forEach((user) => allContainer.append(buddyElement(user)));
  if (statusAnchor && !statusAnchor.isConnected) hideBuddyStatus();
}
function buddyElement(user, action = () => openConversation(user.id)) {
  const item = button('', action, 'buddy');
  const avatar = document.createElement('span'); avatar.className = 'mini-avatar'; avatar.textContent = '☺';
  const names = document.createElement('span'); names.className = 'buddy-info';
  const name = document.createElement('span'); name.textContent = user.display_name;
  const subtitle = document.createElement('small'); subtitle.textContent = user.bio || `@${user.username}`;
  names.append(name, subtitle);
  const dot = document.createElement('span');
  const availability = state.onlineAvailability.get(user.id);
  dot.className = `presence ${statusClasses[availability] || ''}`;
  dot.setAttribute('aria-hidden', 'true');
  item.addEventListener('pointerenter', (event) => {
    if (event.pointerType !== 'touch') showBuddyStatus(item, user);
  });
  item.addEventListener('pointerleave', scheduleBuddyStatusClose);
  item.addEventListener('focus', () => {
    if (item.matches(':focus-visible')) showBuddyStatus(item, user);
  });
  item.addEventListener('blur', scheduleBuddyStatusClose);
  item.addEventListener('click', hideBuddyStatus);
  item.append(avatar, names, dot); return item;
}
async function refreshConversations() {
  const token = state.token;
  const conversations = await api('/conversations');
  if (state.token !== token) return;
  state.conversations = conversations;
  const root = $('conversations'); root.replaceChildren();
  if (!state.conversations.length) {
    const empty = document.createElement('p'); empty.className = 'small muted'; empty.textContent = 'No chats yet.'; root.append(empty);
  }
  for (const conversation of state.conversations) {
    const item = buddyElement(conversation.other_user, () => selectConversation(conversation));
    const subtitle = item.querySelector('small');
    subtitle.textContent = conversation.status ? `↳ ${conversation.status.text}` : 'Direct message';
    item.classList.toggle('active', state.current?.id === conversation.id);
    root.append(item);
  }
  if (statusAnchor && !statusAnchor.isConnected) hideBuddyStatus();
}
async function openConversation(recipientId, statusId) {
  const token = state.token;
  try {
    const payload = { recipient_id: recipientId };
    if (statusId) payload.status_id = statusId;
    const conversation = await api('/conversations', {
      method: 'POST', body: JSON.stringify(payload),
    });
    if (state.token === token) await selectConversation(conversation);
  } catch (error) { showNotice(formatError(error)); }
}

async function endConversation() {
  if (!state.current) return;
  const conversation = state.current;
  const convId = conversation.id;
  const control = $('end-conversation');
  control.disabled = true;
  try {
    await api(`/conversations/${convId}`, { method: 'DELETE' });
    if (state.current !== conversation) return;
    conversation.ended_by_me = true;
    control.textContent = '✕ Waiting for other user...';
    await api(`/conversations/${convId}`);
    if (state.current === conversation) showNotice('Waiting for the other user to end the conversation.');
  } catch (error) {
    if (state.current !== conversation) return;
    if (error.status === 404) {
      clearChat();
      showNotice('This conversation has been ended.');
      await refreshConversations().catch((failure) => showNotice(formatError(failure)));
    } else {
      control.disabled = conversation.ended_by_me;
      showNotice(formatError(error));
    }
  }
}
async function selectConversation(conversation) {
  try {
    clearChat();
    state.current = conversation;
    $('chat-placeholder').hidden = true; $('chat-active').hidden = false;
    $('chat-title').textContent = `💬 ${conversation.other_user.display_name}`;
    $('chat-context').hidden = !conversation.status;
    $('chat-context').textContent = conversation.status ? `📌 Replying to status: “${conversation.status.text}”` : '';
    $('end-conversation').hidden = false;
    $('end-conversation').disabled = conversation.ended_by_me;
    $('end-conversation').textContent = conversation.ended_by_me ? '✕ Waiting for other user...' : '✕ End Conversation';
    await loadHistory(false); await refreshConversations();
  } catch (error) { showNotice(formatError(error)); }
}
async function loadHistory(older) {
  if (!state.current) return;
  const conversation = state.current;
  const convId = conversation.id;
  const offset = older ? state.nextOffset : 0;
  if (offset === null) return;
  const page = await api(`/conversations/${convId}/messages?limit=20&offset=${offset}`);
  if (state.current !== conversation) return;
  const scrollArea = $('messages'); const oldHeight = scrollArea.scrollHeight;
  for (const message of page.items) addMessage(message, true);
  state.nextOffset = page.next_offset;
  $('load-older').hidden = !page.has_more;
  if (older) scrollArea.scrollTop += scrollArea.scrollHeight - oldHeight;
  else scrollArea.scrollTop = scrollArea.scrollHeight;
}
function addMessage(message, prepend = false) {
  if (state.loadedIds.has(message.id) || message.conversation_id !== state.current?.id) return false;
  state.loadedIds.add(message.id);
  // System messages (sender_id is null) are rendered as centered notices
  if (message.sender_id == null) {
    const systemBox = document.createElement('div');
    systemBox.className = 'system-message';
    systemBox.textContent = message.text;
    if (prepend) $('messages').prepend(systemBox); else $('messages').append(systemBox);
    return true;
  }
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
  return true;
}
async function renderMedia(item, placeholder) {
  try {
    const response = await fetch(item.url, { headers: { Authorization: `Bearer ${state.token}` } });
    if (!response.ok) throw new Error('Could not load media');
    const blob = await response.blob();
    if (!placeholder.isConnected) return;
    const objectUrl = URL.createObjectURL(blob);
    state.mediaUrls.add(objectUrl);
    const element = document.createElement(item.content_type.startsWith('video/') ? 'video' : 'img');
    element.src = objectUrl; element.alt = item.original_name;
    if (element.tagName === 'VIDEO') element.controls = true;
    element.addEventListener('error', () => {
      URL.revokeObjectURL(objectUrl);
      state.mediaUrls.delete(objectUrl);
    }, { once: true });
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
    if (state.ws !== ws) return;
    try {
      const packet = JSON.parse(event.data);
      if (packet.type === 'presence.update') { await refreshUsers(); await refreshConversations(); }
      if (packet.type === 'message.new') {
        if (packet.message.conversation_id === state.current?.id) {
          const scrollArea = $('messages'); const nearBottom = scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < 100;
          if (addMessage(packet.message) && state.nextOffset !== null) state.nextOffset += 1;
          if (nearBottom || packet.message.sender_id === state.me.id) scrollArea.scrollTop = scrollArea.scrollHeight;
        }
        await refreshConversations();
      }
      if (packet.type === 'message.error') showNotice(packet.detail);
      if (packet.type === 'conversation.deleted') {
        const deletedId = packet.conversation_id;
        // Remove from conversation list
        state.conversations = state.conversations.filter((c) => c.id !== deletedId);
        if (state.current?.id === deletedId) {
          clearChat();
          showNotice('This conversation has been ended by both users.');
        }
        await refreshConversations();
      }
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
  const conversation = state.current;
  const convId = conversation.id;
  $('send-button').disabled = true;
  try {
    const attachmentIds = [];
    for (const file of files) {
      if (state.current !== conversation) return;
      const form = new FormData(); form.append('file', file);
      const attachment = await api(`/conversations/${convId}/attachments`, { method: 'POST', body: form });
      attachmentIds.push(attachment.id);
    }
    if (state.current !== conversation) return;
    const message = await api(`/conversations/${convId}/messages`, {
      method: 'POST', body: JSON.stringify({ text, attachment_ids: attachmentIds }),
    });
    if (state.current !== conversation) return;
    if (addMessage(message) && state.nextOffset !== null) state.nextOffset += 1;
    $('messages').scrollTop = $('messages').scrollHeight;
    if (input.value === text) input.value = '';
    if (files.length === fileInput.files.length && files.every((file, index) => fileInput.files[index] === file)) {
      fileInput.value = ''; $('file-count').textContent = '';
    }
  } catch (error) {
    if (state.current === conversation) showNotice(formatError(error));
  } finally {
    $('send-button').disabled = false;
    if (state.current === conversation) input.focus();
  }
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
  const token = state.token;
  const submit = $('save-status');
  submit.disabled = true;
  try {
    const status = await api('/users/me/status', {
      method: 'PUT',
      body: JSON.stringify({
        availability: $('status-form').elements.availability.value,
        description: $('status-description').value,
      }),
    });
    if (state.token !== token) return;
    renderMyStatus(status);
    $('status-editor').open = false;
    $('status-editor').querySelector('summary').focus();
    showNotice('Status saved.');
  } catch (error) {
    showNotice(formatError(error));
  } finally {
    submit.disabled = false;
  }
});
$('load-older').addEventListener('click', () => loadHistory(true).catch((error) => showNotice(formatError(error))));
$('send-form').addEventListener('submit', sendMessage);
$('message-text').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('send-form').requestSubmit(); }
});
$('message-files').addEventListener('change', () => { $('file-count').textContent = `${$('message-files').files.length} selected`; });

/* ---------- Search by status keywords ---------- */
async function searchUsers(query) {
  const request = ++searchRequest;
  if (!query.trim()) {
    $('search-results-section').hidden = true;
    return;
  }
  try {
    const encoded = encodeURIComponent(query.trim());
    const data = await api(`/users/search?q=${encoded}`);
    if (request !== searchRequest) return;
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
    if (request === searchRequest) showNotice(formatError(error));
  }
}

$('search-button').addEventListener('click', () => searchUsers($('search-input').value));
$('search-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    searchUsers($('search-input').value);
  }
});

/* ---------- Buddy status tooltip buttons ---------- */
$('buddy-reply-status').addEventListener('click', () => {
  const userId = parseInt(buddyStatus.dataset.userId, 10);
  const statusId = buddyStatus.dataset.statusId;
  if (userId) {
    openConversation(userId, statusId ? parseInt(statusId, 10) : null);
    hideBuddyStatus();
  }
});
$('buddy-start-chat').addEventListener('click', () => {
  const userId = parseInt(buddyStatus.dataset.userId, 10);
  if (userId) {
    openConversation(userId);
    hideBuddyStatus();
  }
});

/* ---------- End conversation button ---------- */
$('end-conversation').addEventListener('click', endConversation);

/* ---------- Dark / Light theme toggle ---------- */
function applyTheme(theme) {
  const isDark = theme === 'dark';
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  localStorage.setItem('theme', theme);
  const toggleBtn = $('theme-toggle');
  if (toggleBtn) toggleBtn.textContent = isDark ? '◑' : '◐';
}

// Initialize theme from localStorage or system preference
(function initTheme() {
  const saved = localStorage.getItem('theme');
  if (saved) {
    applyTheme(saved);
  } else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(prefersDark ? 'dark' : 'light');
  }
})();

$('theme-toggle').addEventListener('click', () => {
  const current = localStorage.getItem('theme') || 'light';
  applyTheme(current === 'dark' ? 'light' : 'dark');
});

if (state.token) boot();
