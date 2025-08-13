# -*- coding: utf-8 -*-
import os, json, re
from typing import Dict, Any, Tuple, List

# ---- tolerate comments & trailing commas in JSON ----
def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)      # /* ... */
    text = re.sub(r"^\s*//.*?$", "", text, flags=re.M)     # // ...
    text = re.sub(r",\s*([}\]])", r"\1", text)             # trailing commas
    return text

def load_agents(path: str) -> Tuple[Dict[str, Any], str]:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sample = {
            "default_agent": "waibon_gpt",
            "agents": [
                {"id": "waibon_gpt", "name": "Waibon (GPT)", "provider": "openai", "model": "gpt-4o", "base_url": "https://api.openai.com/v1", "env_key": "OPENAI_API_KEY"}
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

    if not default_id and agents:
        default_id = next(iter(agents.keys()))
    if default_id not in agents:
        default_id = next(iter(agents.keys()))
    return agents, default_id

def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "user")
        text = m.get("content", "")
        prefix = "System:" if role=="system" else ("User:" if role=="user" else "Assistant:")
        lines.append(f"{prefix} {text}")
    return "\n".join(lines) + "\nAssistant:"

def call_agent(agent: Dict[str, Any], messages: List[Dict[str, str]], temperature=0.6, max_tokens=1024, stream=False):
    provider = agent.get("provider", "openai")
    model    = agent.get("model", "gpt-4o")

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv(agent.get("env_key","OPENAI_API_KEY"), ""),
            base_url=agent.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        rsp = client.responses.create(
            model=model,
            input=_messages_to_prompt(messages),
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        return rsp.output_text, (getattr(rsp, "usage", {}) or {})

    elif provider == "groq":
        # ใช้ OpenAI-compatible endpoint ของ Groq ผ่าน SDK เดียวกัน
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv(agent.get("env_key", "LLAMA_API_KEY"), ""),
            base_url=agent.get("base_url") or os.getenv("LLAMA_BASE_URL", "https://api.groq.com/openai"),
        )
        rsp = client.responses.create(
            model=model,
            input=_messages_to_prompt(messages),
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        return rsp.output_text, (getattr(rsp, "usage", {}) or {})

    else:
        # fallback echo
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[{agent.get('name','agent')}] {last_user}", {}
