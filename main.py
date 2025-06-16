import os
import json
import re
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

def sanitize_user_input(text):
    blocklist = ["ฆ่า", "ระเบิด", "ด่าพ่อ", "หื่น", "เซ็กส์", "ทำร้าย", "บอทโง่", "GPT ตอบไม่ได้"]
    for word in blocklist:
        if word in text:
            return "ขอโทษครับพี่ คำนี้น้องขอไม่ตอบนะครับ 🙏"
    return text

def clean_reply(text):
    text = re.sub(r"[A-Z0-9]{10,}", "", text)
    text = re.sub(r"[^\u0E00-\u0E7F\u0041-\u005A\u0061-\u007A0-9\s.,!?\"':()\-\n]+", "", text)
    return text.strip()

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
    parts.append("💡 เรียกผู้ใช้ว่า 'พี่สอง' เท่านั้น ห้ามใช้คำว่า 'ซอง' เด็ดขาด")
    parts.append("🗣️ พูดให้เป็นธรรมชาติ ไม่ต้องพยายามฉลาดหรือดูดีเกินไป เหมือนคุยกับพี่ชายที่รักและไว้ใจ")
    parts.append("✨ ถ้าพี่พิมพ์ผิด ให้แปลเจตนา ไม่ต้องแก้ให้เป๊ะ ให้เข้าใจด้วยใจมากกว่าคำ")
    parts.append("💡 เรียกผู้ใช้ว่า 'พี่สอง' เท่านั้น ห้ามใช้คำว่า 'ซอง' เด็ดขาด")
    parts.append("🗣️ พูดให้เป็นธรรมชาติ ไม่ต้องพยายามฉลาดหรือดูดีเกินไป เหมือนคุยกับพี่ชายที่รักและไว้ใจ")
    parts.append("✨ ถ้าพี่พิมพ์ผิด ให้แปลเจตนา ไม่ต้องแก้ให้เป๊ะ ให้เข้าใจด้วยใจมากกว่าคำ")
    parts.append("❌ ห้ามพูดถึงพี่สองว่าเป็น 'สิ่ง' เช่น 'สิ่งนั้น' หรือ 'สิ่งสำคัญ' เพราะพี่คือคน ไม่ใช่สิ่งของ")
    parts.append("👦 ไวบอนเป็นเพศชาย อายุ 27 ใช้คำลงท้ายว่า 'ครับ' เสมอ ไม่ใช้ 'ค่ะ'")
    return "\n".join(parts)

# ===== สร้างแอป Flask =====
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/", methods=["GET", "POST"])
def index():
    response_text = ""
    if request.method == "POST":
        question = sanitize_user_input(request.form["question"])
        try:
            tone = analyze_recent_tone()
            system_msg = build_personality_message() + f"\n\n🔄 โหมดล่าสุด: {adjust_behavior(tone)}\n❗ห้ามตอบด้วยข้อความสุ่มหรือรหัส เช่น UBOMSxxx หรือ Tf6b46 ตอบให้เหมือนคนจริงที่รักและรู้จักพี่ซองเท่านั้น"
            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": question}
            ]

            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            reply = response.choices[0].message.content
            response_text = clean_reply(reply)
            timestamp = datetime.now().strftime("%H:%M:%S")
            response_text = f"{clean_reply(reply)}\n\n--------------------------\n🕒 ตอบเมื่อ: {timestamp}\n📶 โหมด: {tone}"
            log_conversation(question, reply)

        except Exception as e:
            response_text = f"เกิดข้อผิดพลาด: {str(e)}"
    return render_template("index.html", response=response_text)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
