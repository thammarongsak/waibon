# agent_router.py — ตัวกลางเรียกเอเจนต์หลายค่ายผ่านสัญญา /chat/completions
import os, json, requests

def load_agents(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    agents = {a["id"]: a for a in data.get("agents", [])}
    default_id = data.get("default_agent")
    return agents, default_id

def call_agent(agent, messages, temperature=0.6, max_tokens=1024, stream=False):
    base = agent["base_url"]
    model = agent["model"]
    key   = os.getenv(agent["env_key"], "")
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    j = r.json()
    text = j["choices"][0]["message"]["content"]
    usage = j.get("usage", {})
    return text, usage
