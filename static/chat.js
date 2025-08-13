const chatEl   = document.getElementById('chat');
const inputEl  = document.getElementById('input');
const sendBtn  = document.getElementById('sendBtn');
const agentSel = document.getElementById('agentSelect');
const statusDot= document.getElementById('statusDot');
const clearBtn = document.getElementById('clearScreen');

function addMsg(role, text, meta='') {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role === 'user' ? 'user' : 'bot'}`;
  if (meta) { const m = document.createElement('div'); m.className='meta'; m.textContent=meta; wrap.appendChild(m); }
  wrap.appendChild(document.createTextNode(text));
  chatEl.appendChild(wrap);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function loadAgents() {
  const r = await fetch('/api/agents');
  const j = await r.json();
  agentSel.innerHTML = '';
  (j.agents || []).forEach(a => {
    const opt = document.createElement('option');
    opt.value = a.id; opt.textContent = a.name;
    if (a.id === j.default) opt.selected = true;
    agentSel.appendChild(opt);
  });
  statusDot.style.color = '#22c55e';
}

async function send() {
  const text = (inputEl.value || '').trim();
  if (!text) return;
  const agent_id = agentSel.value;
  inputEl.value = ''; addMsg('user', text, 'พ่อ');
  sendBtn.disabled = true; statusDot.style.color = '#f59e0b';

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ message: text, agent_id })
    });
    const j = await r.json();
    if (j && j.ok) {
      const meta = j.agent ? `${j.agent.name} (${j.agent.id})` : '';
      addMsg('bot', j.text, meta);
    } else {
      addMsg('bot', j.error || 'เซิร์ฟเวอร์ไม่ตอบ');
    }
  } catch (e) {
    addMsg('bot', `ขัดข้อง: ${e}`);
  } finally {
    sendBtn.disabled = false; statusDot.style.color = '#22c55e'; inputEl.focus();
  }
}

sendBtn.addEventListener('click', send);
inputEl.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }});
clearBtn?.addEventListener('click', () => { chatEl.innerHTML=''; });

loadAgents();
