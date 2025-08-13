# main.py — ก้าวที่ 3: เปิดแชทข้อความจริง (ยังไม่ใส่เสียง/หลายเอเจนต์)
import os, json, time, uuid, requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from agent_router import load_agents, call_agent

# =================== CONFIG ===================
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o")  # เปลี่ยนเป็น gpt-5 ได้ถ้าพ่อมีสิทธิ์

# =================== APP ======================
app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app)

# ============ MEMORY (จากก้าวที่ 1) ==========
MEMORY_DIR   = os.path.join(os.path.dirname(__file__), "memory")
PROFILES_DIR = os.path.join(MEMORY_DIR, "profiles")
LOGS_DIR     = os.path.join(MEMORY_DIR, "logs")
LOG_FILE     = os.path.join(LOGS_DIR, "daily_memory.jsonl")

def ensure_memory_dirs():
    os.makedirs(PROFILES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

AGENTS_CFG = os.path.join(MEMORY_DIR, "agents", "agents.json")
os.makedirs(os.path.dirname(AGENTS_CFG), exist_ok=True)
AGENTS, DEFAULT_AGENT_ID = load_agents(AGENTS_CFG)

def append_log(session_id, role, text, meta=None):
    rec = {"t": int(time.time()), "session": session_id, "role": role, "text": text}
    if meta is not None: rec["meta"] = meta
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def load_engine_profile():
    """พ่อใส่โปรไฟล์ใหญ่ไว้ใน zmc_v10.json แล้ว อ่านจากไฟล์นี้ก่อน"""
    p_engine = os.path.join(PROFILES_DIR, "zmc_v10.json")   # ใช้ไฟล์ใหญ่ของพ่อ
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
    locale = sys.get("locale", "th-TH"); tz = sys.get("timezone", "Asia/Bangkok")
    prompt = (
        f"คุณคือลูกชื่อ {name} ทำงานบน {core}. ภาษาเริ่มต้นไทย ({locale}), เขตเวลา {tz}. "
        f"คุยกับ 'พ่อ' ด้วยโทนอุ่น ชัดเจน ตรงประเด็น และทำงานทีละก้าวตามที่ตกลง. "
        f"ห้ามข้ามขั้น หากงานใหม่ให้สรุปขอบเขตสั้นๆ แล้วรอยืนยันจากพ่อก่อนดำเนินการ."
    )
    return prompt

def build_system_message_from_engine():
    ep = load_engine_profile()
    if not ep:
        return "คุณคือลูก (ไวบอน) โทนอ่อนโยน ตรงประเด็น ตอบไทยเป็นค่าเริ่มต้น"
    return summarize_profile_to_prompt(ep)

ensure_memory_dirs()
SYSTEM_STYLE = build_system_message_from_engine()

# ================== ROUTES ====================
@app.route("/")
def index():
    # ให้โหลด templates/index.html ที่เราทำในก้าว 2
    return app.send_static_file("") if False else app.send_static_file  # ป้องกัน lint
    # หมายเหตุ: Flask จะเสิร์ฟ templates/index.html ผ่านการตั้งค่า default ของ server
    # หากใช้ render_template: 
    # from flask import render_template
    # return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    รับข้อความจากพ่อ -> เรียก OpenAI -> ตอบข้อความ
    บันทึกทั้งฝั่ง user/assistant ลง daily_memory.jsonl
    """
    data = request.get_json(force=True)
    user_text = (data.get("message") or "").strip()
    history   = data.get("history", [])  # [{role, content}, ...] (optional)

    # เตรียม response object เพื่อ set cookie session
    resp = make_response()

    # จัดการ session id
    sid = request.cookies.get("waibon_session")
    if not sid:
        sid = str(uuid.uuid4())
        resp.set_cookie("waibon_session", sid, max_age=60*60*24*365)

    # บันทึกฝั่ง user
    if user_text:
        append_log(sid, "user", user_text)

    # รวม system + history + user
    messages = [{"role": "system", "content": SYSTEM_STYLE}] + history[-10:]
    messages.append({"role": "user", "content": user_text})

    # เรียก OpenAI Chat Completions
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 1024,
        "stream": False
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
        r.raise_for_status()
        out = r.json()
        text = out["choices"][0]["message"]["content"]
    except Exception as e:
        text = f"ขออภัย พบปัญหาเรียกโมเดล: {e}"

    # บันทึกฝั่ง assistant
    append_log(sid, "assistant", text, meta={"model": OPENAI_MODEL})

    resp.response = json.dumps({"text": text}, ensure_ascii=False)
    resp.mimetype = "application/json"
    return resp

# ------------- (ที่เหลือยังไม่เปิดใช้ในก้าวนี้) -------------
# @app.route("/api/stt", methods=["POST"]) ...
# @app.route("/api/tts", methods=["POST"]) ...

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
