# -*- coding: utf-8 -*-
import os, json, re
from typing import Dict, Any, Tuple, List

# ---------- allow comments & trailing commas in agents.json ----------
def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)      # /* ... */
    text = re.sub(r"^\s*//.*?$", "", text, flags=re.M)     # // ...
    text = re.sub(r",\s*([}\]])", r"\1", text)             # trailing commas
    return text

def load_agents(path: str) -> Tuple[Dict[str, Any], str]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        sample = {
            "default_agent": "waibon_gpt",
            "agents": [
                {"id": "waibon_gpt", "name": "Waibon (GPT)",
                 "provider": "openai", "model": "gpt-4o",
                 "base_url": "https://api.openai.com/v1", "env_key": "OPENAI_API_KEY"}
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)

    raw = open(path, "r", encoding="utf-8").read()
    raw = _strip_comments(raw)
    data = json.loads(raw)

    agents: Dict[str, Any] = {}
    default_id = data.get("default_agent") or data.get("default") or ""
    for item in data.get("agents", []):
        aid = item.get("id")
        if not aid: raise ValueError("Agent missing 'id'")
        agents[aid] = item

    if not default_id and agents: default_id = next(iter(agents.keys()))
    if default_id not in agents:  default_id = next(iter(agents.keys()))
    return agents, default_id

def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "user")
        text = m.get("content", "")
        prefix = "System:" if role=="system" else ("User:" if role=="user" else "Assistant:")
        lines.append(f"{prefix} {text}")
    return "\n".join(lines) + "\nAssistant:"

def _messages_for_chat(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role not in ("system","user","assistant"): role = "user"
        out.append({"role": role, "content": content})
    return out

def call_agent(agent: Dict[str, Any], messages: List[Dict[str, str]],
               temperature: float = 0.6, max_tokens: int = 1024, stream: bool = False):
    """
    รองรับทั้ง:
    - OpenAI SDK รุ่นใหม่ (client.responses.create)
    - OpenAI SDK รุ่นเก่า (client.chat.completions.create)
    - Groq (ผ่าน base_url ที่ compatible)
    """
    provider = agent.get("provider", "openai")
    model    = agent.get("model", "gpt-4o")
    base_url = agent.get("base_url") or (os.getenv("OPENAI_BASE_URL") if provider=="openai" else os.getenv("LLAMA_BASE_URL"))
    env_key  = agent.get("env_key", "OPENAI_API_KEY" if provider=="openai" else "LLAMA_API_KEY")
    api_key  = os.getenv(env_key, "")

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 1) Responses API (ใหม่)
    try:
        _ = client.responses  # ถ้าไม่มี attribute นี้จะ throw AttributeError
        rsp = client.responses.create(
            model=model,
            input=_messages_to_prompt(messages),
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        text = getattr(rsp, "output_text", None)
        if text is None and getattr
