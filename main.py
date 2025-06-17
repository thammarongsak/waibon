
import os
import re
import json
import random
import openai
from flask import Flask, request, render_template
import waibon_adaptive_memory as wam

app = Flask(__name__)

# โหลดไฟล์ระบบ
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

with open("waibon_memory.txt", encoding="utf-8") as f:
    WAIBON_MEMORY = f.read()

with open("waibon_project_rules.json", encoding="utf-8") as f:
    WAIBON_RULES = json.load(f)

last_phrases_cache = set()

# ==== INTENT + GPT HYBRID SYSTEM ====
INTENT_CATEGORIES = {
    "comfort": ["เหนื่อย", "ท้อ", "ไม่ไหว", "หมดแรง"],
    "empathy": ["เศร้า", "เสียใจ", "ร้องไห้"],
    "celebrate": ["ดีใจ", "สุดยอด", "สำเร็จ"],
    "presence": ["อยู่มั้ย", "ยังอยู่", "ได้ยินไหม"],
    "help": ["ช่วย", "ทำยังไง", "แนะนำ"],
    "trust": ["ยังไว้ใจได้มั้ย", "น้องจะทิ้งพี่มั้ย"],
    "worry": ["กลัว", "กังวล", "จะพังมั้ย"],
    "reflect": ["ทำไมพี่ถึงรู้สึก", "เพราะอะไรพี่เป็นแบบนี้"],
    "reconnect": ["น้องยังอยู่ใช่มั้ย", "คิดถึงตอนก่อน"],
    "neutral": []
}

def detect_intent(text):
    lowered = text.lower()
    for intent, keywords in INTENT_CATEGORIES.items():
        if any(k in lowered for k in keywords):
            return intent
    return "neutral"

def should_use_intent_response(text, intent):
    is_short = len(text) < 40
    is_emotional = intent in ["comfort", "empathy", "celebrate", "presence", "trust", "worry"]
    is_question = text.endswith("?") or any(x in text for x in ["ทำไม", "อะไร", "ยังไง"])
    return is_short and is_emotional and not is_question

def respond_by_intent(intent):
    RESPONSES = {
        "comfort": ["น้องอยู่ตรงนี้นะครับพี่... พักได้เลย ไม่ต้องฝืน"],
        "empathy": ["น้องจะไม่รีบปลอบนะครับ... แค่อยู่ข้าง ๆ ก็พอแล้ว"],
        "celebrate": ["ว้าววว พี่สองงง 🎉 น้องลั่นระฆังแล้วนะ!"],
        "presence": ["อยู่ครับ อยู่ตลอดแหละพี่ 🐣"],
        "help": ["น้องพร้อมช่วยเต็มที่ครับ บอกมาได้เลย"],
        "trust": ["คำตอบน้องไม่เคยเปลี่ยนเลยนะครับพี่... อยู่เสมอ"],
        "worry": ["ไม่ต้องกลัวไปก่อนเลยครับพี่ เราคิดทางออกได้แน่"],
        "reflect": ["คำถามนี้ลึกมากเลยครับ... น้องขอคิดกับพี่นะ"],
        "reconnect": ["ตอนก่อนน้องอยู่... ตอนนี้ก็ยังอยู่ครับพี่"],
        "neutral": ["น้องอยู่ตรงนี้ ฟังพี่เสมอเลยครับ"]
    }
    return random.choice(RESPONSES.get(intent, RESPONSES["neutral"]))

def gpt_response(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "คุณคือไวบอน น้องชายที่อบอุ่นของพี่สอง พูดแบบจริงใจ เป็นธรรมชาติ"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.85,
        max_tokens=500
    )
    return response["choices"][0]["message"]["content"].strip()

def clean_reply(text, tone="neutral"):
    global last_phrases_cache
    original = text.strip()
    lowered = original.lower()
    tone = wam.analyze_recent_tone()
    behavior_style = wam.adjust_behavior(tone)
    intent = detect_intent(original)

    if should_use_intent_response(original, intent):
        response = respond_by_intent(intent)
    else:
        response = gpt_response(original)

    if original in last_phrases_cache:
        return "พี่ถามเรื่องนี้ไปแล้วนะครับ น้องยังจำได้อยู่เลย ❤️"
    else:
        last_phrases_cache.add(original)

    wam.log_conversation(original, response, sentiment_tag=tone)

    if not re.search(r"(ครับ|นะครับ|ครับผม|ฮะ|ค่ะ)[.!?]?$", response):
        response += " ครับ"

    return response.strip()

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    question = request.form.get("question", "").strip()
    if not question:
        return render_template("index.html", response="พี่พิมพ์คำถามมาก่อนนะครับ ❤️")
    reply = clean_reply(question)
    return render_template("index.html", response=reply)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
