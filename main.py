#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Waibon (Step 1): Text chat + agent switch (OpenAI/Groq) — single, stable bundle.
"""

import os, json, time, uuid, logging
from typing import Dict, Any, Tuple, List
from flask import Flask, request, jsonify, make_response, render_template
from flask_cors import CORS

# ---------------- App & Config ----------------
PORT  = int(os.environ.get("PORT", 10000))
HOST  = os.getenv("HOST", "0.0.0.0")
DEBUG = os.getenv("DEBUG", "false").lower() in {"1","true","yes","on"}

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(
try:
    import openai as _openai
    app.logger.info("OpenAI SDK version = %s", getattr(_openai, "__version__", "unknown"))
except Exception:
    app.logger.warning("OpenAI SDK not importable at boot")

    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
app.logger.info("Waibon backend booting (DEBUG=%s)", DEBUG)

# ---------------- Memory & Paths -------------
BASE_DIR   = os.path.dirname(__file__)
MEM_DIR    = os.path.join(BASE_DIR, "memory")
AGENTS_DIR = os.path.join(MEM_DIR, "agents")
LOGS_DIR   = os.path.join(MEM_DIR, "logs")
LOG_FILE   = os.path.join(LOGS_DIR, "daily_memory.jsonl")

def ensure_dirs():
    os.makedirs(AGENTS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
ensure_dirs()

def append_log(session_id: str, role: str, text: str, meta: Dict[str, Any] | None = None):
    rec = {"t": int(time.time()), "session": session_id, "role": role, "text": text}
    if meta: rec["meta"] = meta
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------------- Agent Router ----------------
from agent_router import load_agents, call_agent  # same-dir file

AGENTS_CFG = os.path.join(AGENTS_DIR, "agents.json")
try:
    AGENTS, DEFAULT_AGENT_ID = load_agents(AGENTS_CFG)
except Exception as e:
    app.logger.error("Failed to load agents.json: %s -> fallback 'echo'", e)
    AGENTS = {"echo": {"id":"echo","name":"Echo Agent","provider":"local","model":"echo"}}
    DEFAULT_AGENT_ID = "echo"

SYSTEM_STYLE = (
    "คุณคือไวบอน ผู้ช่วยของ 'พ่อ' พูดไทยชัด ตรงประเด็น ทำงานทีละก้าว "
    "สรุปสั้นก่อนทำ ต่อไปนี้ตอบแบบกระชับและชัดเจน"
)

# ---------------- Routes ----------------------
@app.get("/healthz")
def healthz():
    return jsonify({"ok": True}), 200

@app.get("/api/agents")
def api_agents():
    items = [{"id": k, "name": v.get("name", k)} for k, v in AGENTS.items()]
    return jsonify({"default": DEFAULT_AGENT_ID, "agents": items}), 200

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/chat")
def api_chat():
    if not request.is_json:
        return jsonify({"ok": False, "error": "Expected application/json"}), 400

    data = request.get_json(silent=True) or {}
    user_text = (data.get("message") or "").strip()
    history   = data.get("history", []) or []
    agent_id  = (data.get("agent_id") or DEFAULT_AGENT_ID)

    resp = make_response()
    sid = request.cookies.get("waibon_session")
    if not sid:
        sid = str(uuid.uuid4())
        resp.set_cookie("waibon_session", sid, max_age=60*60*24*365, httponly=True, samesite="Lax")

    if not user_text:
        resp.response = json.dumps({"ok": False, "error": "Field 'message' is required"}, ensure_ascii=False)
        resp.mimetype = "application/json"
        return resp, 400

    append_log(sid, "user", user_text)

    agent = AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT_ID])
    msgs: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_STYLE}] + history[-10:]
    msgs.append({"role": "user", "content": user_text})

    try:
        reply, usage = call_agent(agent, msgs, temperature=0.6, max_tokens=1024, stream=False)
    except Exception as e:
        reply, usage = f"ขออภัย เกิดข้อผิดพลาดของเอเจนต์: {e}", {}

    append_log(sid, "assistant", reply, meta={"agent": agent.get("id"), "model": agent.get("model"), "usage": usage})

    resp.response = json.dumps({"ok": True, "text": reply, "agent": {"id": agent.get("id"), "name": agent.get("name")}}, ensure_ascii=False)
    resp.mimetype = "application/json"
    return resp, 200

# ---------------- Main ------------------------
if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
