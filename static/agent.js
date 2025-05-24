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

// Keep track of sessions { sid: { li, dot } }
const sessions = {};

// Join the “agents” room so we get broadcast events
socket.emit('join', { role: 'agent' });

// When a new chat starts
socket.on('new_session', data => {
  const { sessionId, lastMessage } = data;
  if (sessions[sessionId]) return;

  const li  = document.createElement('li');
  const dot = document.createElement('span');
  dot.className = 'status-dot grey';
  dot.style.marginRight = '6px';

  li.appendChild(dot);
  li.appendChild(document.createTextNode(`${sessionId} – ${lastMessage}`));
  li.id = `session-${sessionId}`;
  li.onclick = () => openSession(sessionId);

  sessionList.appendChild(li);
  sessions[sessionId] = { li, dot };
});

// Update status (grey, amber, red)
socket.on('status_update', data => {
  const { sessionId, status } = data;
  const session = sessions[sessionId];
  if (!session) return;
  session.dot.className = `status-dot ${status}`;
});

// Incoming user message (while bot still in control)
socket.on('incoming_message', data => {
  const { sessionId, message } = data;
  if (!sessions[sessionId]) {
    socket.emit('new_session', { sessionId, lastMessage: message });
  }
  if (sessionId === currentSession) {
    addMessage('User', message);
  }
  // flag if not current
  sessions[sessionId].dot.classList.replace('grey','amber');
});

// Bot’s reply
socket.on('bot_response', data => {
  const { sessionId, message } = data;
  if (sessionId === currentSession) {
    addMessage('Bot', message);
  }
});

// System messages
socket.on('system_message', data => {
  const { sessionId, message } = data;
  if (sessionId === currentSession) {
    addMessage('System', message);
  }
});

// Open / switch to a session
function openSession(sid) {
  currentSession = sid;
  chatHeader.textContent = sid;
  messages.innerHTML = '';
  btnTakeover.disabled = false;
  btnRelease.disabled  = true;
}

// Send an agent reply
sendBtn.onclick = () => {
  const text = input.value.trim();
  if (!text || !currentSession) return;
  addMessage('Agent', text);
  socket.emit('agent_message', { sessionId: currentSession, message: text });
  input.value = '';
};

// Takeover
btnTakeover.onclick = () => {
  if (!currentSession) return;
  socket.emit('takeover', { sessionId: currentSession });
  btnTakeover.disabled = true;
  btnRelease.disabled  = false;
};

// Release
btnRelease.onclick = () => {
  if (!currentSession) return;
  socket.emit('release', { sessionId: currentSession });
  btnTakeover.disabled = false;
  btnRelease.disabled  = true;
};

// Helper to append a chat bubble
function addMessage(sender, text) {
  const p = document.createElement('p');
  p.textContent = `${sender}: ${text}`;
  messages.appendChild(p);
  messages.scrollTop = messages.scrollHeight;
}
