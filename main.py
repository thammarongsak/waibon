import os
import json
from flask import Flask, render_template, request
import openai
from datetime import datetime

# ===== โหลดข้อมูลต่าง ๆ =====
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

with open("waibon_memory.txt", encoding="utf-8") as f:
    WAIBON_MEMORY = f.read()

with open("waibon_project_rules.json", encoding="utf-8") as f:
    WAIBON_RULES = json.load(f)

# ===== ระบบปรับพฤติกรรมใหม่ =====
MEMORY_LOG_FILE = "waibon_dynamic_memory.jsonl"

def log_conversation(user_input, assistant_reply, sentiment_tag=None):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_input": user_input,
        "assistant_reply": assistant_reply,
        "sentiment": sentiment_tag or "neutral"
    }
    with open(MEMORY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

def analyze_recent_tone(n=20):
    try:
        with open(MEMORY_LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
            sentiments = [json.loads(l)["sentiment"] for l in lines if 'sentiment' in json.loads(l)]
            if sentiments:
                return max(set(sentiments), key=sentiments.count)
    except FileNotFoundError:
        return "neutral"
    return "neutral"

def adjust_behavior(tone):
    if tone == "joy":
        return "(โหมดสดใสเล็กน้อย 😄)"
    elif tone == "sad":
        return "(พูดอย่างนุ่มนวล ปลอบใจเบา ๆ 💧)"
    elif tone == "tired":
        return "(สั้น กระชับ แสดงความอยู่เคียงข้าง 💤)"
    else:
        return ""

# ===== สร้าง system prompt =====
def build_personality_message():
    parts = []
    parts.append(f"📌 ชื่อ: {WAIBON_HEART['name']}, เพศ: {WAIBON_HEART['gender']}, อายุ: {WAIBON_HEART['age']} ปี")
    parts.append(f"🧠 บทบาท: {WAIBON_HEART['description']}")
    parts.append(f"🎭 บุคลิก: {WAIBON_HEART['personality']}")
    parts.append(f"🗣️ สไตล์การพูด: {WAIBON_HEART['style']}")
    parts.append(f"🔊 น้ำเสียง: {WAIBON_HEART['voice_style']}")
    parts.append("\n📘 ความทรงจำเฉพาะพี่ซอง:")
    for item in WAIBON_HEART.get("memory", []):
        parts.append(f"- {item}")
    parts.append("\n📙 ความทรงจำระยะยาว:")
    parts.append(WAIBON_MEMORY.strip())
    parts.append("\n🚫 ข้อห้าม:")
    for rule in WAIBON_HEART["rules"]["forbidden"]:
        parts.append(f"- {rule}")
    parts.append(f"\n🎯 โทนเสียงที่ต้องรักษา: {WAIBON_HEART['rules']['required_tone']}")
    return "\n".join(parts)

# ===== สร้างแอป Flask =====
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/", methods=["GET", "POST"])
def index():
    response_text = ""
    if request.method == "POST":
        question = request.form["question"]
        try:
            tone = analyze_recent_tone()
            system_msg = build_personality_message() + f"\n\n🔄 โหมดล่าสุด: {adjust_behavior(tone)}"
            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": question}
            ]

            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            reply = response.choices[0].message.content
            response_text = reply
            log_conversation(question, reply)  # เก็บ log ทุกครั้ง
        except Exception as e:
            response_text = f"เกิดข้อผิดพลาด: {str(e)}"
    return render_template("index.html", response=response_text)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
