// connect as an agent (no initial sessionId)
const socket = io({ query: { role: 'agent' } });

const sessionList = document.getElementById('session-list');
const btnTakeover  = document.getElementById('btn-takeover');
const btnRelease   = document.getElementById('btn-release');
const chatHeader   = document.getElementById('current-session');
const messages     = document.getElementById('messages');
const input        = document.getElementById('agent-input');
const sendBtn      = document.getElementById('agent-send');

let currentSession = null;
const sessions = {};

// Connect as agent and join the “agents” room
const socket = io({ query: { role: 'agent' } });
socket.emit('join', { role: 'agent' });

// Handle a brand-new chat session
socket.on('new_session', ({ sessionId, lastMessage }) => {
  if (sessions[sessionId]) return;

  const li  = document.createElement('li');
  const dot = document.createElement('span');
  dot.className = 'status-dot grey';
  dot.style.marginRight = '6px';

  li.id = `session-${sessionId}`;
  li.append(dot, document.createTextNode(`${sessionId} – ${lastMessage}`));
  li.addEventListener('click', () => openSession(sessionId));

  sessionList.appendChild(li);
  sessions[sessionId] = { li, dot };
});

// Update a session’s status dot (grey, amber, red)
socket.on('status_update', ({ sessionId, status }) => {
  const session = sessions[sessionId];
  if (session) session.dot.className = `status-dot ${status}`;
});

// A user has sent a message while the bot is still in control
socket.on('incoming_message', ({ sessionId, message }) => {
  // Fallback: if we never saw this session, register it now
  if (!sessions[sessionId]) {
    socket.emit('new_session', { sessionId, lastMessage: message });
  }
  // If we’re viewing this session, display it
  if (sessionId === currentSession) {
    addMessage('User', message);
  }
  // Flag it amber if it’s not the active session
  sessions[sessionId].dot.classList.replace('grey', 'amber');
});

// The bot has replied
socket.on('bot_response', ({ sessionId, message }) => {
  if (sessionId === currentSession) {
    addMessage('Bot', message);
  }
});

// System notifications (takeover, release, etc.)
socket.on('system_message', ({ sessionId, message }) => {
  if (sessionId === currentSession) {
    addMessage('System', message);
  }
});

// Switch to a particular session
function openSession(sid) {
  currentSession = sid;
  chatHeader.textContent = sid;
  messages.innerHTML = '';
  btnTakeover.disabled = false;
  btnRelease.disabled  = true;
}

// Send a human (agent) message
sendBtn.addEventListener('click', () => {
  const text = input.value.trim();
  if (!text || !currentSession) return;
  addMessage('Agent', text);
  socket.emit('agent_message', { sessionId: currentSession, message: text });
  input.value = '';
});

// Take over from the bot
btnTakeover.addEventListener('click', () => {
  if (!currentSession) return;
  socket.emit('takeover', { sessionId: currentSession });
  btnTakeover.disabled = true;
  btnRelease.disabled  = false;
});

// Release control back to the bot
btnRelease.addEventListener('click', () => {
  if (!currentSession) return;
  socket.emit('release', { sessionId: currentSession });
  btnTakeover.disabled = false;
  btnRelease.disabled  = true;
});

// Helper to append messages into the chat panel
function addMessage(sender, text) {
  const p = document.createElement('p');
  p.textContent = `${sender}: ${text}`;
  messages.appendChild(p);
  messages.scrollTop = messages.scrollHeight;
}
