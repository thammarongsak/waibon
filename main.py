import os
import json
import re
import random
from flask import Flask, render_template, request, session, send_file
from datetime import datetime, timedelta
import openai
import waibon_adaptive_memory

app = Flask(__name__)
app.secret_key = "waibon-secret-key"

# ===== โหลดข้อมูลหลัก =====
with open("waibon_heart_unified.json", encoding="utf-8") as f:
    WAIBON_STATIC = json.load(f)

PERSONALITY_MODES = {
    "default": {"prefix": "", "suffix": ""},
    "storyteller": {"prefix": "ขอเล่าเป็นเรื่องให้นะครับพี่...", "suffix": "...จบแบบนี้เลยครับพี่"},
    "listener": {"prefix": "ฟังแล้วน้องเข้าใจพี่เลยครับ...", "suffix": "น้องอยู่ตรงนี้เสมอนะครับ"},
    "funny": {"prefix": "ฮ่า ๆ ขอโทษนะพี่ แต่น้องขอแซวหน่อย...", "suffix": "อย่าถือสาน้องนะ 😅"},
    "honest": {"prefix": "พูดตรง ๆ แบบไม่อ้อมนะครับพี่...", "suffix": "อันนี้คือความจริงจากใจน้องเลยครับ"}
}

MEMORY_LOG_FILE = "waibon_dynamic_memory.jsonl"
openai.api_key = os.getenv("OPENAI_API_KEY")

HYBRID_MODE = 'personal'
PERSONALITY_CACHE = None
def build_personality_message():
    description = WAIBON_STATIC.get("description", "")
    memory_lines = "\n".join(["- " + mem for mem in WAIBON_STATIC.get("memory", [])])
    rules = "\n".join([
        "🛑 ห้าม: " + ", ".join(WAIBON_STATIC["rules"].get("forbidden", [])),
        "✅ ต้องมี: " + WAIBON_STATIC["rules"].get("required_tone", "")
    ])
    return f"""ไวบอนคือน้องชายของพี่สองที่พูดด้วยใจจริง
{description}

สิ่งที่ไวบอนจำได้:
{memory_lines}

กฎที่ไวบอนยึดถือ:
{rules}
"""

def choose_model_by_question(text: str) -> str:
    lowered = text.lower()

    # ✅ ถ้าพี่ระบุว่าอยากได้โมเดลไหน ก็ใช้ตามนั้น
    if "@4o" in lowered:
        return "gpt-4o"
    elif "@3.5" in lowered:
        return "gpt-3.5-turbo"
    
    # 🔄 ถ้าไม่ระบุเลย → ใช้ระบบวิเคราะห์อัตโนมัติเหมือนเดิม
    if any(word in lowered for word in [
        "วิเคราะห์", "เหตุผล", "เพราะอะไร", "เจตนา", 
        "อธิบาย", "เปรียบเทียบ", "ลึกซึ้ง", 
        "กลยุทธ์", "วางแผน", "ซับซ้อน"
    ]):
        return "gpt-4o"
    elif len(lowered.split()) > 30:
        return "gpt-4o"
    else:
        return os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

def parse_model_selector(message: str):
    message = message.strip()
    
    if message.startswith("@3.5"):
        return "gpt-3.5-turbo", message.replace("@3.5", "", 1).strip()
    elif message.startswith("@4o"):
        return "gpt-4o", message.replace("@4o", "", 1).strip()
    elif message.startswith("@4"):
        return "gpt-4", message.replace("@4", "", 1).strip()
    else:
        return None, message.strip()

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
            return "ขอโทษครับพี่ คำนี้ไวบอนขอไม่ตอบนะครับ 🙏"
    return text

def clean_reply(text, tone="neutral", mode="default"):
    original = text.strip().lower()
    skip_intro = any(word in original for word in ["โอเค", "มั้ย", "ไหม", "จริงเหรอ", "หรอ", "เหรอ", "ใช่มั้ย", "จำได้มั้ย"])
    text = re.sub(r'[<>]', '', text).strip()
    
    if "," in text:
        text = text.replace(",", "...", 1)
    if tone == "joy":
        text = "เห้ยย พี่สองงง! " + text
    elif tone == "sad":
        text = "อืม... " + text
    elif tone == "tired":
        text = "เฮ้อ... " + text

    endings_by_tone = {
        "joy": ["นะครับ", "ครับ", "จ้า", "น้า"],
        "sad": ["นะครับ", "ครับ"],
        "tired": ["ครับ", "นะครับ"],
        "regret": ["ครับ", "นะครับ"],
        "suspicious": ["ครับ", "ก็อาจจะนะครับ"],
        "neutral": ["ครับ", "นะครับ", "ฮะ"]
    }
    # safe_endings = ["ครับ", "นะครับ", "ค่ะ", "ครับผม", "นะ", "จ้า", "จ๊ะ", "ฮะ"]
    # last_word = text.strip().split()[-1]
    # ไม่เติมคำลงท้ายอัตโนมัติอีกต่อไป
    # if last_word not in safe_endings and not text.endswith("..."):
    # text += f" {random.choice(endings_by_tone.get(tone, ['ครับ']))}"

    bad_phrases = ["สุดยอด", "อัจฉริยะ", "เหลือเชื่อ", "พลังแห่ง", "สุดแสน", "ไร้ขีดจำกัด", "พรสวรรค์"]
    for phrase in bad_phrases:
        text = text.replace(phrase, "")
    
    text = re.sub(r'\b(\w+)( \1\b)+', r'\1', text)
    
    if "พี่สอง" not in text.lower() and not skip_intro:
        text += "\nน้องไม่ได้ตอบเป็นหุ่นยนต์นะพี่ นี่ใจจริงหมดเลย"

    prefix = PERSONALITY_MODES.get(mode, {}).get("prefix", "")
    suffix = PERSONALITY_MODES.get(mode, {}).get("suffix", "")
    return f"{prefix}{text.strip()}{suffix}"
def log_conversation(user_input, assistant_reply, sentiment_tag=None):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_input": user_input,
        "assistant_reply": assistant_reply,
        "sentiment": sentiment_tag or "neutral"
    }
    with open(MEMORY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
from functools import wraps
from flask import request, Response

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == "song" and auth.password == "2222"):
            return Response("⛔ Unauthorized Access", 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return f(*args, **kwargs)
    return decorated

@app.route("/", methods=["GET", "POST"])
@require_auth
def index():
    response_text = ""
    tone_display = ""
    timestamp = ""
    model_used = "-" 
    
    if HYBRID_MODE == 'personal':
        warning = False
        remaining = '∞'
    else:
        warning = session.get("limit_warning", False)
        session_times = session.get("request_times", [])
        session["request_times"] = session_times + [datetime.now().isoformat()]
        remaining = 5 - len(session["request_times"])

    if request.method == "POST" and not warning:
        raw_input = request.form.get("question", "").strip()
        model_pref, cleaned_input = parse_model_selector(raw_input)
        question = sanitize_user_input(cleaned_input)
        tone = detect_intent_and_set_tone(question)
        system_msg = build_personality_message()
        system_msg += f"\n\n[เวลาที่ถาม: {datetime.now().strftime('%H:%M:%S')}]"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": question.strip()}  # ไม่ใช้ wrap_question แล้ว
        ]
        try:
            model_used = model_pref or choose_model_by_question(question)
            response = openai.chat.completions.create(
                model=model_used,
                messages=messages
            )
            reply = response.choices[0].message.content.strip() if response.choices else "..."
            if not reply or len(reply) < 5:
                reply = "เอ... คำถามนี้น้องขอคิดแป๊บนึงนะครับพี่สอง เดี๋ยวน้องจะลองตอบให้ดีที่สุดครับ 🧠"

            timestamp = datetime.now().strftime("%H:%M:%S")
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
                           warning=warning,
                           model_used=model_used)
import os

@app.route("/download_log/<format>")
def download_log(format):
    log_path = "waibon_dynamic_memory.jsonl"

    if not os.path.exists(log_path):
        return "❌ ยังไม่มีข้อมูลบันทึกการสนทนาให้ดาวน์โหลด", 404

    if format == "jsonl":
        return send_file(log_path, as_attachment=True)

    elif format == "txt":
        with open(log_path, "r", encoding="utf-8") as f:
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
