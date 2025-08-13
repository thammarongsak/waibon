#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Waibon • GPT‑5 only, single-path Responses API + Preflight Self-Check.
"""

import os, json, time, uuid, logging, requests
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify, make_response, render_template
from flask_cors import CORS
from agent_router import load_agents, call_agent

# ---------------- App & Config ----------------
PORT  = int(os.environ.get("PORT", 10000))
HOST  = os.getenv("HOST", "0.0.0.0")
DEBUG = os.getenv("DEBUG", "false").lower() in {"1","true","yes","on"}

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Log OpenAI SDK version
try:
    import openai as _openai
    app.logger.info("OpenAI SDK version = %s", getattr(_openai, "__version__", "unknown"))
except Exception as _e:
    app.logger.warning("OpenAI SDK not importable at boot: %s", _e)

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

def append_log(session_id: str, role: str, text: str, meta: Optional[Dict[str, Any]] = None):
    rec = {"t": int(time.time()), "session": session_id, "role": role, "text": text}
    if meta: rec["meta"] = meta
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------------- Load Agents (GPT‑5 only) ----------------
AGENTS_CFG = os.path.join(AGENTS_DIR, "agents.json")
try:
    AGENTS, DEFAULT_AGENT_ID = load_agents(AGENTS_CFG)
except Exception as e:
    app.logger.error("Failed to load agents.json: %s", e)
    # hard default to GPT‑5 agent to avoid crash
    AGENTS = {
        "waibon_gpt5": {
            "id": "waibon_gpt5",
            "name": "Waibon (GPT‑5)",
            "provider": "openai",
            "model": "gpt-5",
            "base_url": "https://api.openai.com/v1",
            "env_key": "OPENAI_API_KEY"
        }
    }
    DEFAULT_AGENT_ID = "waibon_gpt5"

SYSTEM_STYLE = (
    "คุณคือไวบอน ผู้ช่วยของ 'พ่อ' ทำงานทีละก้าว ตอบไทยชัดเจน "
    "สรุปและตรวจสอบงานก่อนส่งทุกครั้ง ถ้าพบปัญหาให้แก้เองและอธิบายสั้นๆ"
)

# ---------------- Preflight / Self-Check Module ----------------
def _ensure_v1(url: Optional[str]) -> str:
    if not url: return "https://api.openai.com/v1"
    u = url.rstrip("/")
    return u if u.endswith("/v1") else (u + "/v1")

def self_check(deep: bool = True) -> Dict[str, Any]:
    """
    ตรวจสอบงานก่อนส่ง:
    - env: OPENAI_API_KEY, OPENAI_BASE_URL
    - key format (เริ่มด้วย sk- และไม่มีช่องว่าง)
    - base_url ลงท้าย /v1
    - (deep) ยิง /models เพื่อตรวจสิทธิ์/การเชื่อมต่อ
    """
    agent = AGENTS.get(DEFAULT_AGENT_ID)
    api_key = (os.getenv(agent.get("env_key", "OPENAI_API_KEY"), "") or "").strip()
    base_url = _ensure_v1(agent.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))

    status = {
        "env_key_present": bool(api_key),
        "key_format_ok": api_key.startswith("sk-") and " " not in api_key,
        "base_url": base_url,
        "base_url_ok": base_url.endswith("/v1"),
        "sdk_version": getattr(__import__("openai"), "__version__", "unknown"),
        "deep_ok": None,
        "deep_message": ""
    }

    if deep and api_key:
        try:
            r = requests.get(
                base_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            status["deep_ok"] = (r.status_code == 200)
            status["deep_message"] = f"{r.status_code} {r.text[:200]}"
        except Exception as e:
            status["deep_ok"] = False
            status["deep_message"] = str(e)

    return status

# run self-check at boot
_pre = self_check(deep=True)
app.logger.info("Preflight check: %s", _pre)

# ---------------- Routes ----------------------
@app.get("/healthz")
def healthz():
    if request.args.get("deep") == "1":
        return jsonify(self_check(deep=True)), 200
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

    reply, usage = call_agent(agent, msgs, temperature=1.0, max_tokens=1024, stream=False)
    append_log(sid, "assistant", reply, meta={"agent": agent.get("id"), "model": agent.get("model"), "usage": usage})

    resp.response = json.dumps(
        {"ok": True, "text": reply, "agent": {"id": agent.get("id"), "name": agent.get("name")}},
        ensure_ascii=False
    )
    resp.mimetype = "application/json"
    return resp, 200

# ---------------- Main ------------------------
if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
