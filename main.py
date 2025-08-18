# ====== เพิ่มด้านบน (import) ======
import traceback

# ====== แทนที่ฟังก์ชัน ensure_responses_api แบบเดิม ======
def ensure_responses_api():
    if not hasattr(client, "responses"):
        raise RuntimeError(
            "OpenAI SDK ไม่มี `client.responses`. ให้ pin openai==1.55.3 แล้ว Clear build cache + Deploy ใหม่"
        )

# ====== แก้ /healthz เดิม ให้เลือก ping ภายนอกได้ ======
@app.get("/healthz")
def healthz():
    """
    ?ping=1  -> ทดลองเรียก OpenAI /models (อาจล้มถ้าคีย์ผิด/เน็ตออกไม่ได้)
    ?ping=0  -> เช็คแค่ SDK ภายใน (แนะนำเริ่มจาก 0)
    """
    try:
        ensure_responses_api()
        ping = request.args.get("ping", "0") == "1"
        detail = {"sdk": "responses", "ok": True}

        if ping:
            import requests
            r = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                timeout=8,
            )
            detail.update({"ping": True, "status": r.status_code})
            if r.status_code != 200:
                # ไม่ถือว่า 500—บอกเหตุชัด ๆ เพื่อแก้ได้
                return jsonify({"ok": False, "reason": "openai_ping_failed", **detail}), 200
        else:
            detail["ping"] = False

        return jsonify(detail), 200
    except Exception as e:
        app.logger.exception("healthz failed")
        return jsonify({"ok": False, "error": str(e)}), 200  # อย่า 500

# ====== ครอบ /api/chat ด้วย try/except ======
@app.post("/api/chat")
def api_chat():
    try:
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

        msgs = [{"role": "system", "content": SYSTEM_STYLE}]
        for m in history[-10:]:
            if isinstance(m, dict) and m.get("role") and m.get("content"):
                msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": user_text})

        agent = AGENTS.get(agent_id, AGENTS[DEFAULT_AGENT_ID])
        result = call_openai_responses(agent, msgs)
        reply  = result["text"]
        usage  = result.get("usage", {})

        append_log(sid, "user", user_text)
        append_log(sid, "assistant", reply, meta={"agent": agent.get("id"), "model": agent.get("model"), "usage": usage})

        resp.response = json.dumps(
            {"ok": True, "text": reply, "agent": {"id": agent.get("id"), "name": agent.get("name")}},
            ensure_ascii=False
        )
        resp.mimetype = "application/json"
        return resp, 200

    except Exception as e:
        app.logger.exception("api_chat failed")
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 200

# ====== Global error handler (กัน 500 เงียบ) ======
@app.errorhandler(Exception)
def on_error(e):
    app.logger.exception("unhandled exception")
    return jsonify({"ok": False, "error": str(e), "type": e.__class__.__name__}), 200
