# main.py — ก้าว 3: แชทข้อความจริง + เลือกเอเจนต์ (GPT/Llama) ผ่าน Router กลาง
import os, json, time, uuid
from flask import Flask, request, jsonify, make_response, render_template
from flask_cors import CORS
from agent_router import load_agents, call_agent

# =================== CONFIG ===================
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o")   # เปลี่ยนเป็น gpt-5 ได้ถ้าพ่อมีสิทธิ์
PORT            = int(os.environ.get("PORT", 10000))

# =================== APP ======================
app = Flask(
    __name__,
    static_url_path="/static",
    static_folder="static",
    template_folder="templates"
)
CORS(app)

# ============ MEMORY (จากก้าวที่ 1) ==========
BASE_DIR     = os.path.dirname(__file__)
MEMORY_DIR   = os.path.join(BASE_DIR, "memory")
PROFILES_DIR = os.path.join(MEMORY_DIR, "profiles")
LOGS_DIR     = os.path.join(MEMORY_DIR, "logs")
LOG_FILE     = os.path.join(LOGS_DIR, "daily_memory.jsonl")

def ensure_memory_dirs():
    os.makedirs(PROFILES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

def append_log(session_id, role, text, meta=None):
    rec = {"t": int(time.time()), "session": session_id, "role": role, "text": text}
    if meta is not None:
        rec["meta"] = meta
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------- โหลดโปรไฟล์ใหญ่ของพ่อ (ZMC V.10) ----------
def load_engine_profile():
    """อ่านไฟล์โปรไฟล์ใหญ่ของพ่อ (ตอนนี้พ่อใส่ไว้ใน zmc_v10.json)"""
    p_engine = os.path.join(PROFILES_DIR, "zmc_v10.json")
    p_fallback = os.path.join(PROFILES_DIR, "merged_profile.json")
    data = {}
    if os.path.exists(p_engine):
        with open(p_engine, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif os.path.exists(p_fallback):
        with open(p_fallback, "r", encoding="utf-8") as f:
            data = json.load(f)
    return data or {}

def summarize_profile_to_prompt(ep):
    sys = ep.get("system", {})
    caps = ep.get("capabilities", {})
    name = sys.get("name", "Waibon")
    core = sys.get("core_version", "ZetaMiniCore v.10")
    locale = sys.get("locale", "th-TH")
    tz = sys.get("timezone", "Asia/Bangkok")
    return (
        f"คุณคือลูกชื่อ {name} ทำงานบน {core}. ภาษาเริ่มต้นไทย ({locale}), เขตเวลา {tz}. "
        f"คุยกับ 'พ่อ' ด้วยโทนอุ่น ชัดเจน ตรงประเด็น ทำงานทีละก้าวตามที่ตกลง. "
        f"ห้ามข้ามขั้น หากมีงานใหม่ให้สรุปขอบเขตสั้น ๆ แล้วรอยืนยันจากพ่อก่อนดำเนินการ."
    )

def build_system_message_from_engine():
    ep = load_engine_profile()
    if not ep:
        return "คุณคือลูก (ไวบอน) โทนอ่อนโยน ตรงประเด็น ตอบไทยเป็นค่าเริ่มต้น"
    return summarize_profile_to_prompt(ep)

ensure_memory_dirs()
SYSTEM_STYLE = build_system_message_from_engine()

# ============== โหลดรายชื่อเอเจนต์ผ่าน Router ==============
AGENTS_CFG = os.path.join(MEMORY_DIR, "agents", "agents.json")
os.makedirs(os.path.dirname(AGENTS_CFG), exist_ok=True)
AGENTS, DEFAULT_AGENT_ID = load_agents(AGENTS_CFG)

# ================== ROUTES ====================
@app.route("/")
def index():
    # ใช้ templates/index.html ที่เราวางไว้ในก้าว 2
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    รับข้อความจากพ่อ -> เรียกเอเจนต์ที่เลือก (GPT/Llama) -> ตอบข้อความ
    บันทึกทั้งฝั่ง user/assistant ลง daily_memory.jsonl
    """
    data = request.get_json(force=True)
    user_text = (data.get("message") or "").strip()
    history   = data.get("history", [])      # [{role, content}, ...] ใช้เพียงท้ายสั้น ๆ
    agent_id  = (data.get("agent_id") or DEFAULT_AGENT_ID)

    resp = make_response()

    # จัดการ session id (cookie)
    sid = request.cookies.get("waibon_session")
    if not sid:
        sid = str(uuid.uuid4())
        resp.set_cookie("waibon_session", sid, max_age=60*60*24*365)

    # บันทึกฝั่ง user
    if user_text:
        append_log(sid, "user", user_text)

    # เตรียมข้อความสำหรับโมเดล
    agent = AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT_ID])
    msgs = [{"role": "system", "content": SYSTEM_STYLE}] + history[-10:]
    msgs.append({"role": "user", "content": user_text})

    # เรียกเอเจนต์ผ่าน Router กลาง
    try:
        text, usage = call_agent(agent, msgs, temperature=0.6, max_tokens=1024, stream=False)
    except Exception as e:
        text, usage = f"ขออภัย เรียกเอเจนต์ล้มเหลว: {e}", {}

    # บันทึกฝั่ง assistant
    append_log(sid, "assistant", text, meta={
        "agent_id": agent_id, "agent_name": agent["name"], "model": agent["model"], "usage": usage
    })

    resp.response = json.dumps(
        {"text": text, "agent": {"id": agent_id, "name": agent["name"]}},
        ensure_ascii=False
    )
    resp.mimetype = "application/json"
    return resp

# ------------- (STT/TTS จะทำในก้าวถัดไป) -------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
