// Mockup logic (ยังไม่เรียก API จริง) — ใช้ทดสอบ UI และพฤติกรรมพื้นฐาน

const chatEl   = document.getElementById("chat");
const inputEl  = document.getElementById("input");
const sendBtn  = document.getElementById("send");
const micDict  = document.getElementById("micDict");
const micPTT   = document.getElementById("micPTT");
const clearBtn = document.getElementById("clearView");
const saveBtn  = document.getElementById("saveProject");
const projUL   = document.getElementById("projectList");
const newProj  = document.getElementById("newProject");
const speaking = document.getElementById("speaking");
const attach   = document.getElementById("attach");
const agentPicker = document.getElementById("agentPicker");

let currentProject = "default";
let agents = ["waibon"]; // mock
let isRecordingPTT = false;

// helper: timestamp เล็ก ๆ
function ts() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2,"0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// helper: เพิ่มบับเบิล
function addBubble({who, name, text}) {
  const b = document.createElement("div");
  b.className = `bubble ${who === "user" ? "me" : "bot"}`;
  b.innerHTML = `
    <div class="meta">
      <span class="name">${name}</span>
      <span class="timestamp">${ts()}</span>
    </div>
    <div class="text"></div>`;
  b.querySelector(".text").textContent = text;
  chatEl.appendChild(b);
  chatEl.scrollTop = chatEl.scrollHeight;  // เลื่อนขึ้นด้านบนแบบ GPT (คงท้ายหน้าจอ)
}

async function sendMessage() {
  const msg = inputEl.value.trim();
  if (!msg) return;

  // เพิ่มบับเบิลฝั่งพ่อ (ซ้าย/ขวาตาม theme ปัจจุบัน)
  addBubble({ who: "user", name: "พ่อ", text: msg });

  // เคลียร์กล่องและโฟกัสกลับทันที
  inputEl.value = "";
  inputEl.focus();

  // แสดงกำลังประมวลผล (คลื่น)
  speaking.classList.remove("hidden");

  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        history: []  // ระยะแรกยังไม่ส่งยาว (กันรก) — ค่อยเพิ่มทีหลัง
      })
    });
    const data = await r.json();
    const answer = data.text || "(ไม่มีคำตอบ)";
    
    // ใส่ชื่อเอเจนต์เริ่มต้นเป็น Waibon (หลายเอเจนต์จะทำในก้าวถัดไป)
    const agent_id = document.getElementById("agentPicker").value || "waibon_gpt";
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, history: [], agent_id })
    });
    const data = await r.json();
    const agentName = (data.agent && data.agent.name) || "Agent";
    addBubble({ who: "bot", name: agentName, text: data.text || "(ไม่มีคำตอบ)" });
    
    addBubble({ who: "bot", name: "Waibon", text: answer });
  } catch (e) {
    addBubble({ who: "bot", name: "Waibon", text: "เรียก /api/chat ไม่สำเร็จ" });
  } finally {
    speaking.classList.add("hidden");
  }
}


// ปุ่มส่ง & Enter
sendBtn.onclick = sendMessage;
inputEl.addEventListener("keydown", (e)=>{
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ปุ่มเคลียร์วิว (ไม่ลบความจำจริง)
clearBtn.onclick = ()=>{ chatEl.innerHTML = ""; inputEl.focus(); };

// ปุ่มบันทึกโปรเจ็กต์ (mock)
saveBtn.onclick = ()=>{ alert("จะบันทึกบทสนทนาเป็นโปรเจ็กต์ (ผูก API ในก้าวถัดไป)"); };

// โปรเจ็กต์ mock
function addProject(name){
  const li = document.createElement("li");
  li.textContent = name;
  li.onclick = ()=>{ currentProject = name; };
  projUL.appendChild(li);
}
["default","demo-1"].forEach(addProject);
newProj.onclick = ()=>{
  const name = prompt("ตั้งชื่อโปรเจ็กต์");
  if(name){ addProject(name); }
};

// ไมค์ 2 โหมด (mock UI เท่านั้น)
micDict.onclick = ()=>{
  speaking.classList.remove("hidden");
  setTimeout(()=>{
    speaking.classList.add("hidden");
    inputEl.value = (inputEl.value + " " + "[เสียงถอดเป็นข้อความ]").trim();
    inputEl.focus();
  }, 1200);
};

micPTT.onmousedown = ()=>{
  isRecordingPTT = true;
  speaking.classList.remove("hidden");
};
micPTT.onmouseup = ()=>{
  if(!isRecordingPTT) return;
  isRecordingPTT = false;
  setTimeout(()=>{ // ตอบกลับ ~3s หลังพูดจบ
    speaking.classList.add("hidden");
    addBubble({who:"bot", name:"Waibon", text:"ตอบกลับหลัง PTT ~3s (mock)"});
  }, 3000);
};

// แนบไฟล์ (mock)
attach.onchange = ()=>{
  if(attach.files?.length){
    addBubble({who:"user", name:"พ่อ", text:`แนบไฟล์ ${attach.files.length} รายการ (mock)`});
    inputEl.focus();
  }
};

// เติม timestamp ให้บับเบิลที่อยู่ใน HTML ตั้งต้น
document.querySelectorAll(".bubble .timestamp").forEach(el=> el.textContent = ts());
inputEl.focus();  // โฟกัสช่องพิมพ์เมื่อโหลด
