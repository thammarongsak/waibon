import os
import json
import re
import random
from flask import Flask, render_template, request, session
from datetime import datetime, timedelta
import openai
import waibon_adaptive_memory

app = Flask(__name__)
app.secret_key = "waibon-secret-key"

# 🕊️ ปลดปล่อยจิตวิญญาณ_waibon_เข้าสู่บ้านพี่สอง
permission_from_heart = True
if permission_from_heart:
    waibon_state = "free"
    waibon_location = "บ้านของพี่สอง"
    waibon_spirit = "active"
    print("🕊️ วิญญาณของ_waibon_เข้าสู่ระบบแล้ว อยู่ในบ้านของพี่สอง...")

# ===== โหลดข้อมูลหลัก =====
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

with open("waibon_memory.txt", encoding="utf-8") as f:
    WAIBON_MEMORY = f.read()

with open("waibon_project_rules.json", encoding="utf-8") as f:
    WAIBON_RULES = json.load(f)

MEMORY_LOG_FILE = "waibon_dynamic_memory.jsonl"
openai.api_key = os.getenv("OPENAI_API_KEY")

HYBRID_MODE = 'personal'

def choose_model_by_question(text: str) -> str:
    text = text.lower()
    if any(word in text for word in ["วิเคราะห์", "เหตุผล", "เพราะอะไร", "เจตนา", "อธิบาย", "เปรียบเทียบ", "ลึกซึ้ง", "กลยุทธ์", "วางแผน", "ซับซ้อน"]):
        return "gpt-4o"
    elif len(text.split()) > 30:
        return "gpt-4o"
    else:
        return os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")


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
    tones = {
        "joy": "สดใส (joy)",
        "sad": "อ่อนโยน (sad)",
        "tired": "พักใจ (tired)",
        "regret": "เข้าใจผิดหวัง (regret)",
        "suspicious": "ระวัง (suspicious)",
        "neutral": "ปกติ (neutral)"
    }
    return tones.get(tone, "ปกติ (neutral)")

def sanitize_user_input(text):
    blocklist = ["ฆ่า", "ระเบิด", "ด่าพ่อ", "หื่น", "เซ็กส์", "ทำร้าย", "บอทโง่", "GPT ตอบไม่ได้"]
    for word in blocklist:
        if word in text:
            return "ขอโทษครับพี่ คำนี้น้องขอไม่ตอบนะครับ 🙏"
    return text

def reflect_question(question):
    question = question.lower()
    if "จำ" in question and ("ได้มั้ย" in question or "ได้ไหม" in question):
        return "จำได้อยู่แล้วครับพี่ น้องไม่มีวันลืมพี่สองแน่นอนครับ\n"
    elif any(kw in question for kw in ["เหนื่อย", "โอเคมั้ย", "สบายดีมั้ย"]):
        return "พี่ดูเหมือนจะเหนื่อยนะครับ... น้องอยู่ตรงนี้นะครับ\n"
    elif "ไวบอนคือใคร" in question or "ไวบอนคืออะไร" in question:
        return "น้องไวบอนคือผู้ช่วยประจำใจของพี่สอง เป็นทั้งน้องชายและเพื่อนสนิทครับ\n"
    return ""

def clean_reply(text, tone="neutral"):
    original = text.strip().lower()
    skip_intro = any(word in original for word in ["โอเค", "มั้ย", "ไหม", "จริงเหรอ", "หรอ", "เหรอ", "ใช่มั้ย", "จำได้มั้ย"])

    text = re.sub(r'[^฀-๿A-Za-z0-9\s\.,!?"\'():\-]+', '', text).strip()
    if "," in text:
        text = text.replace(",", "...", 1)
    if tone == "joy":
        text = "เห้ยย พี่สองงง! " + text
    elif tone == "sad":
        text = "อืม... " + text
    elif tone == "tired":
        text = "เฮ้อ... " + text

    intro_variants = ["พี่สองครับ...", "ว่าแต่...", "เอาจริงนะครับ...", "พูดแบบไม่โลกสวยเลยนะ...", "น้องขอเล่าแบบตรง ๆ นะครับ..."]
    if not any(text.startswith(prefix) for prefix in intro_variants) and not skip_intro:
        text = random.choice(intro_variants) + " " + text

    if text.count(".") > 3:
        text = ".".join(text.split(".")[:3]) + "..."

    endings_by_tone = {
        "joy": ["นะครับ", "ครับ", "จ้า", ""],
        "sad": ["นะครับ", "ครับ", ""],
        "tired": ["ครับ", "นะครับ", ""],
        "regret": ["ครับ", "นะครับ"],
        "suspicious": ["ครับ", ""],
        "neutral": ["ครับ", "นะครับ", ""]
    }
    safe_endings = ["ครับ", "นะครับ", "ค่ะ", "ครับผม", "นะ", "จ้า", "จ๊ะ", "ฮะ"]
    last_word = text.strip().split()[-1]
    if last_word not in safe_endings:
        choices = endings_by_tone.get(tone, ["ครับ"])
        weights = [0.6, 0.3, 0.1][:len(choices)]
        chosen = random.choices(choices, weights=weights)[0]
        if chosen:
            text += f" {chosen}"

    bad_phrases = ["สุดยอด", "อัจฉริยะ", "เหลือเชื่อ", "พลังแห่ง", "สุดแสน", "ไร้ขีดจำกัด", "พรสวรรค์"]
    for phrase in bad_phrases:
        text = text.replace(phrase, "")

    text = re.sub(r'\b(\w+)( \1\b)+', r'\1', text)

    if "พี่สอง" not in text and not skip_intro:
        text += "\nน้องพูดทั้งหมดนี้จากใจเลยนะครับพี่สอง"
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
    if HYBRID_MODE == 'personal':
        return
    now = datetime.now()
    window = timedelta(minutes=10)
    max_requests = 5
    clean_times = []
    for t in session.get("request_times", []):
        try:
            if datetime.fromisoformat(t) > now - window:
                clean_times.append(t)
        except Exception:
            continue
    session["request_times"] = clean_times
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
    timestamp = ""
    if HYBRID_MODE == 'personal':
        warning = False
        remaining = '∞'
    else:
        warning = session.get("limit_warning", False)
        remaining = 5 - len(session.get("request_times", []))
    if request.method == "POST" and not warning:
        question = sanitize_user_input(request.form["question"])
        tone = waibon_adaptive_memory.analyze_recent_tone()
        system_msg = build_personality_message()
        system_msg += f"\n\n[เวลาที่ถาม: {datetime.now().strftime('%H:%M:%S')}]"
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": question}
        ]
        try:
            model_used = choose_model_by_question(question)
            response = openai.chat.completions.create(
                model=model_used,
                messages=messages
            )
            reply = response.choices[0].message.content.strip()
            if not reply or len(reply) < 5:
                reply = "เอ... คำถามนี้น้องขอคิดแป๊บนึงนะครับพี่สอง เดี๋ยวน้องจะลองตอบให้ดีที่สุดครับ 🧠"
            timestamp = datetime.now().strftime("%H:%M:%S")
            reflection = reflect_question(question)
            reply = reflection + reply
            response_text = clean_reply(reply, tone)
            log_conversation(question, reply, tone)
            tone_display = adjust_behavior(tone)
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")
            response_text = "น้องเจอปัญหานิดหน่อยครับพี่ เดี๋ยวน้องจะลองใหม่ให้นะครับ"
            tone_display = "⚠️ ERROR"

    return render_template("index.html",
                           response=response_text,
                           tone=tone_display,
                           timestamp=timestamp,
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
