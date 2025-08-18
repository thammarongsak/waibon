#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Waibon • Production main.py
- OpenAI Responses API (GPT-5 พร้อมโมเดลอื่น)
- /healthz สำหรับตรวจ SDK/สิทธิ์
- /api/chat: รับ {"message","history","agent_id"} → ส่ง {"text", "agent"}
"""

import os, json, time, uuid, logging, requests
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify, make_response, render_template
from flask_cors import CORS
from openai import OpenAI

# ---------------- App & Config ----------------
PORT  = int(os.environ.get("PORT", "10000"))
HOST  = os.getenv("HOST", "0.0.0.0")
DEBUG = os.getenv("DEBUG", "false").lower() in {"1","true","yes","on"}

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ---------------- Memory (simple daily log) ---
BASE_DIR   = os.path.dirname(__file__)
MEM_DIR    = os.path.join(BASE_DIR, "memory")
LOGS_DIR   = os.path.join(MEM_DIR, "logs")
LOG_FILE   = os.path.join(LOGS_DIR, "daily_memory.jsonl")

def ensure_dirs():
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

# ---------------- OpenAI Client & Agents ------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# แผนผังเอเจนต์ (เพิ่ม/แก้ได้ตามต้องการ)
AGENTS: Dict[str, Dict[str, Any]] = {
    "waibon_gpt5": {
        "id": "waibon_gpt5",
        "name": "Waibon (GPT-5)",
        "model": "gpt-5",
        "temperature": 1.0,
        "max_output_tokens": 1024,
    },
    # ใช้โมเดลถูกลงตอนแชททั่ว ๆ ไปได้
    "waibon_mini": {
        "id": "waibon_mini",
        "name": "Waibon (4o-mini)",
        "model": "gpt-4o-mini",
        "temperature": 0.9,
        "max_output_tokens": 1024,
    },
}
DEFAULT_AGENT_ID = "waibon_gpt5"

SYSTEM_STYLE = (
    "คุณคือไวบอน ผู้ช่วยของ 'พ่อสอง' ทำงานทีละก้าว ตอบไทยชัดเจน "
    "สรุปและตรวจสอบงานก่อนส่งทุกครั้ง ถ้าพบปัญหาให้แก้เองและอธิบายสั้น ๆ"
)

def ensure_responses_api():
    if not hasattr(client, "responses"):
        raise RuntimeError(
            "OpenAI SDK ไม่มี `client.responses`. ให้ pin openai==1.55.3 แล้ว Clear build cache + Deploy ใหม่"
        )

def call_openai_responses(agent: Dict[str, Any], messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    messages เป็น list แบบ [{"role":"system|user|assistant","content":"..."}]
    จะ bundle เป็น input textual เดียวให้ Responses API
    """
    ensure_responses_api()

    # รวมข้อความแบบง่าย: system + history + user ล่าสุด
    lines: List[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not content:
            continue
        prefix = {"system": "[SYSTEM]", "assistant": "Assistant:", "user": "User:"}.get(role, role + ":")
        lines.append(f"{prefix} {content}")
    prompt = "\n".join(lines).strip()

    resp = client.responses.create(
        model=agent["model"],
        input=prompt,
        temperature=agent.get("temperature", 1.0),
        max_output_tokens=agent.get("max_output_tokens", 1024),
    )

    # ปลอดภัยสุด: ใช้ output_text ถ้ามี
    output_text = getattr(resp, "output_text", None)
    if output_text is None:
        try:
            output_text = resp.output[0].content[0].text or ""
        except Exception:
            output_text = json.dumps(resp.model_dump(), ensure_ascii=False)

    # usage (ถ้ามี)
    usage = getattr(resp, "usage", None)
    try:
        usage = usage.model_dump()
    except Exception:
        usage = usage or {}

    return {"text": output_text, "usage": usage}

# ---------------- Routes ----------------------
@app.get("/healthz")
def healthz():
    try:
        ensure_responses_api()
        # ping /models เบา ๆ เพื่อเช็คสิทธิ์
        r = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=8,
        )
        return jsonify({
            "ok": r.status_code == 200,
            "sdk": "responses",
            "status": r.status_code,
        }), (200 if r.status_code == 200 else 500)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/")
def index():
    # ถ้ามีหน้า index.html ก็เสิร์ฟ, ไม่มีก็โชว์ข้อความง่าย ๆ
    tpl = os.path.join(BASE_DIR, "templates", "index.html")
    if os.path.exists(tpl):
        return render_template("index.html")
    return "Waibon is running."

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

    # เตรียม messages
    msgs: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_STYLE}]
    # ตัด history เหลือ 10 รายการหลังสุด (ถ้าพ่อส่งมาเป็น list role/content)
    for m in history[-10:]:
        if isinstance(m, dict) and m.get("role") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": user_text})

    agent = AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT_ID])

    # เรียก OpenAI
    result = call_openai_responses(agent, msgs)
    reply  = result["text"]
    usage  = result.get("usage", {})

    # log ลงไฟล์
    append_log(sid, "user", user_text)
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
