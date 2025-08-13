#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Waibon backend (robust): ทำงานได้แม้ยังไม่มี Flask-Cors / templates / agents.json
"""

import os, json, time, uuid, logging
from typing import Dict, Any, Tuple
from flask import Flask, request, jsonify, make_response

# ---------- CORS (fallback ถ้ายังไม่ติดตั้ง) ----------
try:
    from flask_cors import CORS  # pip install Flask-Cors
    _HAS_CORS = True
except Exception:
    _HAS_CORS = False
    def CORS(app, *_, **__):
        app.logger.warning("Flask-Cors not installed. Install with: pip install Flask-Cors")
        return app

# ---------- agent_router (fallback ถ้ายังไม่พร้อม) ----------
try:
    from agent_router import load_agents, call_agent  # ต้องมีไฟล์ agent_router.py
    _HAS_ROUTER = True
except Exception as e:
    _HAS_ROUTER = False
    _ROUTER_ERR = str(e)

    def load_agents(_path: str) -> Tuple[Dict[str, Any], str]:
        # สร้างเอเจนต์เทียมไว้ก่อน (echo)
        agents = {
            "echo": {"id": "echo", "name": "Echo Agent", "model": "local-echo"}
        }
        return agents, "echo"

    def call_agent(agent: Dict[str, Any], msgs, temperature=0.6, max_tokens=1024, stream=False):
        # ตอบกลับข้อความสุดท้ายแบบ echo
        last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        text = f"[{agent['name']}] {last_user}"
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "note": "router-fallback"}
        return text, usage

# =================== CONFIG ===================
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o")  # เปลี่ยนเป็น gpt-5 ได้ถ้ามีสิทธิ์
PORT            = int(os.environ.get("PORT", 10000))
HOST            = os.getenv("HOST", "0.0.0.0")
DEBUG           = os.getenv("DEBUG", "false").lower() in {"1","true","yes","on"}

# =================== APP ======================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
app.logger.info("Waibon backend starting (DEBUG=%s, CORS=%s, router=%s)", DEBUG, _HAS_CORS, _HAS_ROUTER)
if not _HAS_ROUTER:
    app.logger.warning("agent_router fallback in use: %s", _ROUTER_ERR if '_ROUTER_ERR' in globals() else "unknown")

# ============ MEMORY เมื่อก่อนก้าว 1 ==========
BASE_DIR     = os.path.dirname(__file__)
MEMORY_DIR   = os.path.join(BASE_DIR, "memory")
PROFILES_DIR = os.path.join(MEMORY_DIR, "profiles")
LOGS_DIR     = os.path.join(MEMORY_DIR, "logs")
AGENTS_DIR   = os.path.join(MEMORY_DIR, "agents")
LOG_FILE     = os.path.join(LOGS_DIR, "daily_memory.jsonl")

def ensure_memory_dirs():
    os.makedirs(PROFILES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(AGENTS_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

def append_log(session_id, role, text, meta=None):
    rec = {"t": int(time.time()), "session": session_id, "role": role, "text": text}
    if meta is not None:
        rec["meta"] = meta
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------- โหลดโปรไฟล์พ่อ (optional) ----------
def load_engine_profile():
    p_engine = os.path.join(PROFILES_DIR, "zmc_v10.json")
    p_fallback = os.path.join(PROFILES_DIR, "merged_profile.json")
    for p in (p_engine, p_fallback):
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}

def summarize_profile_to_prompt(ep):
    sys = ep.get("system", {})
    name = sys.get("name", "Waibon")
    core = sys.get("core_version", "ZetaMiniCore v.10")
    locale = sys.get("locale", "th-TH")
    tz = sys.get("timezone", "Asia/Bangkok")
    return (
        f"คุณคือลูกชื่อ {name} ทำงานบน {core}. ภาษาเริ่มต้นไทย ({locale}), เขตเวลา {tz}. "
        f"คุยกับ 'พ่อ' ด้วยโทนอุ่น ชัดเจน ตรงประเด็น ทำงานทีละก้าวตามที่ตกลง. "
        f"ห้ามข้ามขั้น หากมีงานใหม่ให้สรุปขอบเขตสั้น ๆ แล้วรอยืนยันจากพ่อก่อนดำเนินการ."
    )

ensure_memory_dirs()
SYSTEM_STYLE = summarize_profile_to_prompt(load_engine_profile())

# ============== โหลดรายชื่อเอเจนต์ผ่าน Router ==============
AGENTS_CFG = os.path.join(AGENTS_DIR, "agents.json")
AGENTS, DEFAULT_AGENT_ID = load_agents(AGENTS_CFG)
if DEFAULT_AGENT_ID not in AGENTS:
    # ป้องกันเคสไฟล์ว่าง/เสีย
    DEFAULT_AGENT_ID = next(iter(AGENTS.keys()))

# ================== ROUTES ====================
@app.get("/")
def root():
    # ลดปัญหา template หาย: ตอบ JSON ไปเลย
    return jsonify({
        "ok": True,
        "service": "waibon-backend",
        "message": "Waibon API is running.",
        "router_ready": _HAS_ROUTER,
        "cors_ready": _HAS_CORS,
        "default_agent": DEFAULT_AGENT_ID
    }), 200

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "status": "healthy"}), 200

@app.post("/api/chat")
def api_chat():
    """
    body: { message: str, history?: [{role, content}], agent_id?: str }
    """
    if not request.is_json:
        return jsonify({"ok": False, "error": "Expected application/json"}), 400

    data = request.get_json(silent=True) or {}
    user_text = (data.get("message") or "").strip()
    history   = data.get("history", []) or []
    agent_id  = (data.get("agent_id") or DEFAULT_AGENT_ID)
    agent     = AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT_ID])

    resp = make_response()

    # session cookie
    sid = request.cookies.get("waibon_session")
    if not sid:
        sid = str(uuid.uuid4())
        resp.set_cookie("waibon_session", sid, max_age=60*60*24*365, httponly=True, samesite="Lax")

    if not user_text:
        resp.response = json.dumps({"ok": False, "error": "Field 'message' is required"}, ensure_ascii=False)
        resp.mimetype = "application/json"
        return resp, 400

    # log user
    append_log(sid, "user", user_text)

    msgs = [{"role": "system", "content": SYSTEM_STYLE}] + history[-10:]
    msgs.append({"role": "user", "content": user_text})

    try:
        text, usage = call_agent(agent, msgs, temperature=0.6, max_tokens=1024, stream=False)
    except Exception as e:
        text, usage = f"ขออภัย เรียกเอเจนต์ล้มเหลว: {e}", {}

    # log assistant
    append_log(sid, "assistant", text, meta={"agent_id": agent.get("id"), "agent_name": agent.get("name"), "model": agent.get("model"), "usage": usage})

    resp.response = json.dumps({"ok": True, "text": text, "agent": {"id": agent.get("id"), "name": agent.get("name")}}, ensure_ascii=False)
    resp.mimetype = "application/json"
    return resp, 200

# ----------------- MAIN -----------------
if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
