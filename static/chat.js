// ====== Elements ======
const chatEl   = document.getElementById('chat');
const inputEl  = document.getElementById('input');
const sendBtn  = document.getElementById('sendBtn');
const statusDot= document.getElementById('statusDot');
const statusTx = document.getElementById('statusText');
const clearBtn = document.getElementById('clearScreen');

// ====== UI helpers ======
function addMsg(role, text, meta='', cls='') {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role === 'user' ? 'user' : 'bot'} ${cls||''}`.trim();
  if (meta) { const m = document.createElement('div'); m.className='meta'; m.textContent=meta; wrap.appendChild(m); }
  wrap.appendChild(document.createTextNode(text));
  chatEl.appendChild(wrap);
  chatEl.scrollTop = chatEl.scrollHeight;
}
function setBusy(busy, msg) {
  sendBtn.disabled = !!busy;
  statusDot.style.color = busy ? '#f59e0b' : '#22c55e';
  if (statusTx) statusTx.textContent = msg || (busy ? 'กำลังส่ง…' : 'พร้อม');
}

// ====== Preflight (ฝั่งหน้า: แค่ช่วยเตือน) ======
function quickPrecheck() {
  // แค่แจ้งเตือนกรณีเสี่ยงทั่วไป เพื่อช่วยพ่อดีบักไว
  // 1) โปรโตคอล: ถ้าเปิดหน้าเว็บผ่าน file:// ให้เตือน
  if (location.protocol === 'file:') {
    addMsg('bot', 'เตือน: กรุณาเปิดผ่านโดเมน/พอร์ตของเซิร์ฟเวอร์ ไม่ใช่ file://', 'ระบบ', 'warn');
  }
}
quickPrecheck();

// ====== Send flow ======
async function send() {
  const text = (inputEl.value || '').trim();
  if (!text) return;
  inputEl.value = '';
  addMsg('user', text, 'พ่อ');
  setBusy(true);

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ message: text }) // pattern เดิมของพ่อ: ไม่มี agent selector
    });

    // Handle non-200
    if (!r.ok) {
      const body = await r.text().catch(()=> '');
      addMsg('bot', `ขัดข้อง: ${r.status} ${r.statusText}\n${body}`, 'ระบบ', 'error');
      return;
    }

    const j = await r.json().catch(()=> ({}));
    if (j && (j.text || j.error)) {
      const meta = j.agent ? `${j.agent.name} (${j.agent.id})` : 'Waibon';
      const isErr = (j.text || '').startsWith('[ระบบ] SDK OpenAI') || (j.text || '').includes('(error)');
      addMsg('bot', j.text || j.error || 'ไม่มีข้อความตอบกลับ', meta, isErr ? 'error' : '');
    } else {
      addMsg('bot', 'ไม่มีข้อความตอบกลับจากเซิร์ฟเวอร์', 'ระบบ', 'warn');
    }
  } catch (e) {
    addMsg('bot', `ขัดข้องฝั่งหน้า: ${e}`, 'ระบบ', 'error');
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

// ====== Events ======
sendBtn.addEventListener('click', send);
inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
clearBtn?.addEventListener('click', () => { chatEl.innerHTML = ''; });
