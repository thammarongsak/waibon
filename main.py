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


# === 🔧 เพิ่มจากการอัปเดตล่าสุด ===


import os
import json
import re
from flask import Flask, render_template, request, session
from datetime import datetime, timedelta
import openai

app = Flask(__name__)
app.secret_key = "waibon-secret-key"

# ===== โหลดข้อมูลหลัก =====
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

with open("waibon_memory.txt", encoding="utf-8") as f:
    WAIBON_MEMORY = f.read()

with open("waibon_project_rules.json", encoding="utf-8") as f:
    WAIBON_RULES = json.load(f)

MEMORY_LOG_FILE = "waibon_dynamic_memory.jsonl"
openai.api_key = os.getenv("OPENAI_API_KEY")

# ===== Intent-Based Tone Detection =====
def detect_intent_and_set_tone(user_input: str) -> str:
    user_input = user_input.lower()
    if any(kw in user_input for kw in ["เหนื่อย", "ไม่ไหว", "เพลีย", "ล้า", "หมดแรง"]):
        return "tired"
    elif any(kw in user_input for kw in ["เสียใจ", "เศร้า", "ร้องไห้", "ผิดหวัง"]):
        return "sad"
    elif any(kw in user_input for kw in ["ดีใจ", "สุดยอด", "เยี่ยม", "สุขใจ", "ดีมาก"]):
        return "joy"
    elif any(kw in user_input for kw in ["ขอโทษ", "รู้สึกผิด", "ผิดเอง"]):
        return "regret"
    elif any(kw in user_input for kw in ["โกหก", "หลอก", "ไม่จริง"]):
        return "suspicious"
    else:
        return "neutral"

def adjust_behavior(tone):
    if tone == "joy":
        return "สดใส (joy)"
    elif tone == "sad":
        return "อ่อนโยน (sad)"
    elif tone == "tired":
        return "พักใจ (tired)"
    elif tone == "regret":
        return "เข้าใจผิดหวัง (regret)"
    elif tone == "suspicious":
        return "ระวัง (suspicious)"
    else:
        return "ปกติ (neutral)"

def sanitize_user_input(text):
    blocklist = ["ฆ่า", "ระเบิด", "ด่าพ่อ", "หื่น", "เซ็กส์", "ทำร้าย", "บอทโง่", "GPT ตอบไม่ได้"]
    for word in blocklist:
        if word in text:
            return "ขอโทษครับพี่ คำนี้น้องขอไม่ตอบนะครับ 🙏"
    return text

def clean_reply(text):
    text = re.sub(r"[A-Z0-9]{10,}", "", text)
    text = re.sub(r'[^฀-๿A-Za-z0-9\s.,!?\"\'():\-\n]+', '', text)
    return text.strip()

def log_conversation(user_input, assistant_reply, sentiment_tag=None):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_input": user_input,
        "assistant_reply": assistant_reply,
        "sentiment": sentiment_tag or "neutral"
    }
    with open(MEMORY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

@app.before_request
def limit_request_rate():
    now = datetime.now()
    window = timedelta(minutes=10)
    max_requests = 5

    if "request_times" not in session:
        session["request_times"] = []

    # คัดเฉพาะรายการในช่วงเวลา
    session["request_times"] = [t for t in session["request_times"] if datetime.fromisoformat(t) > now - window]

    if request.endpoint == "index" and request.method == "POST":
        if len(session["request_times"]) >= max_requests:
            session["limit_warning"] = True
        else:
            session["request_times"].append(now.isoformat())
            session["limit_warning"] = False

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
    return "\n".join(parts)

@app.route("/", methods=["GET", "POST"])
def index():
    response_text = ""
    tone_display = ""
    remaining = 5 - len(session.get("request_times", []))
    warning = session.get("limit_warning", False)

    if request.method == "POST" and not warning:
        question = sanitize_user_input(request.form["question"])
        tone = detect_intent_and_set_tone(question)
        tone_display = adjust_behavior(tone)

        system_msg = build_personality_message()
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": question}
        ]

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            reply = response.choices[0].message.content
            timestamp = datetime.now().strftime("%H:%M:%S")
            clean = clean_reply(reply)
            response_text = f"{clean}\n\n--------------------------\n🕒 ตอบเมื่อ: {timestamp}  📶 โหมด: {tone_display}"
            log_conversation(question, reply, tone)
        except Exception as e:
            response_text = f"เกิดข้อผิดพลาด: {str(e)}"

    return render_template("index.html",
                           response=response_text,
                           tone=tone_display,
                           remaining=remaining,
                           warning=warning)

@app.route("/download_log/<format>")
def download_log(format):
    from flask import send_file
    if format == "jsonl":
        return send_file("waibon_dynamic_memory.jsonl", as_attachment=True)
    elif format == "txt":
        with open("waibon_dynamic_memory.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()
        txt = "\n".join([line.strip() for line in lines])
        with open("waibon_convo.txt", "w", encoding="utf-8") as f:
            f.write(txt)
        return send_file("waibon_convo.txt", as_attachment=True)
    else:
        return "Invalid format", 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
