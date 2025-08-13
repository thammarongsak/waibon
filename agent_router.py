# -*- coding: utf-8 -*-
import os, json, re
from typing import Dict, Any, Tuple, List, Optional

# ---------- JSON utilities (allow comments & trailing commas) ----------
def _strip_json(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)      # /* ... */
    text = re.sub(r"^\s*//.*?$", "", text, flags=re.M)     # // ...
    text = re.sub(r",\s*([}\]])", r"\1", text)             # trailing commas
    return text

def _ensure_v1(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    u = url.rstrip("/")
    return u if u.endswith("/v1") else (u + "/v1")

def _is_gpt5(model: str) -> bool:
    return model.lower().startswith("gpt-5")

# ---------- Load agents (GPT‑5 first) ----------
def load_agents(path: str) -> Tuple[Dict[str, Any], str]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        sample = {
            "default_agent": "waibon_gpt5",
            "agents": [
                {
                    "id": "waibon_gpt5",
                    "name": "Waibon (GPT‑5)",
                    "provider": "openai",
                    "model": "gpt-5",
                    "base_url": "https://api.openai.com/v1",
                    "env_key": "OPENAI_API_KEY"
                }
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)

    raw = open(path, "r", encoding="utf-8").read()
    data = json.loads(_strip_json(raw))

    agents: Dict[str, Any] = {}
    default_id = data.get("default_agent") or data.get("default") or ""
    for item in data.get("agents", []):
        aid = item.get("id")
        if not aid:
            raise ValueError("Agent missing 'id'")
        if item.get("base_url"):
            item["base_url"] = _ensure_v1(item["base_url"])
        agents[aid] = item

    if not default_id and agents:
        default_id = next(iter(agents.keys()))
    if default_id not in agents:
        default_id = next(iter(agents.keys()))
    return agents, default_id

# ---------- Prompt builder ----------
def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "user")
        text = m.get("content", "")
        prefix = "System:" if role == "system" else ("User:" if role == "user" else "Assistant:")
        lines.append(f"{prefix} {text}")
    return "\n".join(lines) + "\nAssistant:"

# ---------- Main caller (robust to missing .responses) ----------
def call_agent(
    agent: Dict[str, Any],
    messages: List[Dict[str, str]],
    temperature: float = 1.0,     # GPT‑5: จะไม่ถูกส่ง (ใช้ค่า default=1)
    max_tokens: int = 1024,
    stream: bool = False          # (ยังไม่ใช้ในชุดนี้)
):
    """
    เส้นทางหลัก: Responses API (openai>=1.x)
    - ใช้ max_completion_tokens
    - ถ้าเป็น GPT‑5 จะไม่ส่ง temperature
    หาก SDK ไม่มี `.responses` -> ไม่ล้ม แต่ส่งข้อความอธิบายให้ผู้ใช้ (UI) แทน
    """
    from openai import OpenAI

    model    = agent.get("model", "gpt-5")
    base_url = _ensure_v1(agent.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    api_key  = (os.getenv(agent.get("env_key", "OPENAI_API_KEY"), "") or "").strip()

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = _messages_to_prompt(messages)

    # ลองใช้ Responses API (ถ้า SDK รองรับ)
    try:
        # ถ้า SDK เก่า attribute นี้จะไม่มี -> AttributeError
        _ = client.responses
        kwargs = {
            "model": model,
            "input": prompt,
            "max_completion_tokens": max_tokens
        }
        # GPT‑5 ไม่ให้กำหนด temperature
        if not _is_gpt5(model):
            kwargs["temperature"] = temperature

        rsp = client.responses.create(**kwargs)

        # ดึงข้อความออกจากผลลัพธ์
        text = getattr(rsp, "output_text", None)
        if text is None:
            parts = []
            for c in getattr(rsp, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    parts.append(t)
            text = "".join(parts)
        usage = getattr(rsp, "usage", {}) or {}
        return (text or "").strip(), dict(usage)

    except AttributeError:
        # SDK ที่รันอยู่ไม่มี Responses API -> ส่งคำอธิบายกลับไปให้ UI (กันแอปล้ม)
        msg = (
            "[ระบบ] SDK OpenAI ในสภาพแวดล้อมนี้ยังไม่มี Responses API (client.responses) \n"
            "วิธีแก้: แก้ requirements ให้เป็น openai==1.55.3 แล้วกด Clear build cache + Deploy ใหม่บน Render\n"
            "หมายเหตุ: GPT‑5 ต้องใช้ Responses API เท่านั้น"
        )
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"{msg}\n\n(ข้อความล่าสุดของพ่อ): {last_user}", {}

    except Exception as e:
        # ข้อผิดพลาดอื่น ๆ (เช่น คีย์/สิทธิ์/โมเดล)
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[Waibon] (error) {last_user}\n\nรายละเอียดข้อผิดพลาด: {e}", {}
