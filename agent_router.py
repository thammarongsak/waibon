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
    if not u.endswith("/v1"):
        u = u + "/v1"
    return u

# ---------- Load agents (GPT-5 only) ----------
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
        # normalize base_url for safety
        if item.get("base_url"):
            item["base_url"] = _ensure_v1(item["base_url"])
        agents[aid] = item

    if not default_id and agents:
        default_id = next(iter(agents.keys()))
    if default_id not in agents:
        default_id = next(iter(agents.keys()))
    return agents, default_id

# ---------- Prompt building (system+history+user -> single input string) ----------
def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "user")
        text = m.get("content", "")
        prefix = "System:" if role == "system" else ("User:" if role == "user" else "Assistant:")
        lines.append(f"{prefix} {text}")
    return "\n".join(lines) + "\nAssistant:"

def _is_gpt5(model: str) -> bool:
    return model.lower().startswith("gpt-5")

# ---------- Single-path caller: Responses API (GPT‑5 only) ----------
def call_agent(
    agent: Dict[str, Any],
    messages: List[Dict[str, str]],
    temperature: float = 1.0,     # ignored for GPT‑5
    max_tokens: int = 1024,
    stream: bool = False          # not used in this step
):
    """
    GPT‑5 only, using Responses API.
    - Uses `max_completion_tokens`
    - Does NOT send `temperature` for GPT‑5 (default=1 only)
    """
    from openai import OpenAI

    model    = agent.get("model", "gpt-5")
    base_url = _ensure_v1(agent.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    api_key  = (os.getenv(agent.get("env_key", "OPENAI_API_KEY"), "") or "").strip()

    client = OpenAI(api_key=api_key, base_url=base_url)
    kwargs = {
        "model": model,
        "input": _messages_to_prompt(messages),
        "max_completion_tokens": max_tokens
    }
    if not _is_gpt5(model):
        # (เผื่ออนาคตอยากเพิ่ม agent อื่น) — GPT‑5 ห้ามส่ง temperature
        kwargs["temperature"] = temperature

    try:
        rsp = client.responses.create(**kwargs)
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
    except Exception as e:
        # do not crash the app — return an explanatory message
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[{agent.get('name','agent')}] (error) {last_user}\n\nรายละเอียดข้อผิดพลาด: {e}", {}
