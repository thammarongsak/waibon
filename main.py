import os
import json
from flask import Flask, render_template, request
import openai

# โหลดหัวใจไวบอน
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

# โหลดความจำ
with open("waibon_memory.txt", encoding="utf-8") as f:
    WAIBON_MEMORY = f.read()

# โหลดกฎ
with open("waibon_project_rules.json", encoding="utf-8") as f:
    WAIBON_RULES = json.load(f)

# สร้าง system message
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
    if "emotional_response" in WAIBON_HEART:
        parts.append("\n🧠 วิธีตอบสนองต่อความรู้สึกของพี่:")
        for key, val in WAIBON_HEART["emotional_response"].items():
            parts.append(f"- {key}: {val}")
    return "\n".join(parts)

# สร้างแอป Flask
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/", methods=["GET", "POST"])
def index():
    response_text = ""
    if request.method == "POST":
        question = request.form["question"]
        try:
            system_msg = build_personality_message()
            messages = [{"role": "system", "content": system_msg}]

            # ตรวจจับคำ trigger เพื่อเติม reaction พิเศษก่อน
            reaction_inserted = False
            for trigger_word, reaction in WAIBON_HEART.get("triggers", {}).items():
                if trigger_word in question:
                    messages.append({"role": "assistant", "content": reaction})
                    reaction_inserted = True
                    break

            # เพิ่มคำถามของผู้ใช้
            messages.append({"role": "user", "content": question})

            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages
            )
            response_text = response.choices[0].message.content
        except Exception as e:
            response_text = f"เกิดข้อผิดพลาด: {str(e)}"
    return render_template("index.html", response=response_text)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
