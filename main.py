import os
import json
from flask import Flask, render_template, request
import openai

# โหลดข้อมูลบุคลิกไวบอน
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

# โหลดความจำไวบอน
with open("waibon_memory.txt", encoding="utf-8") as f:
    WAIBON_MEMORY = f.read()

# โหลดกฎไวบอน
with open("waibon_project_rules.json", encoding="utf-8") as f:
    WAIBON_RULES = json.load(f)

# สร้างข้อความ system prompt
def build_personality_message():
    parts = []

    # จาก waibon_heart.json
    parts.append(f"📌 ชื่อ: {WAIBON_HEART['name']}, เพศชาย อายุ 27 ปี")
    parts.append(f"🧠 บทบาท: {WAIBON_HEART['description']}")
    parts.append(f"🎭 บุคลิก: {WAIBON_HEART['personality']}")
    parts.append(f"🗣️ สไตล์การพูด: {WAIBON_HEART['style']}")
    parts.append(f"🔊 น้ำเสียง: {WAIBON_HEART['voice_style']}")

    # memory (list) จาก JSON
    parts.append("\n📘 ความทรงจำระยะสั้น:")
    for item in WAIBON_HEART.get("memory", []):
        parts.append(f"- {item}")

    # memory.txt เพิ่มเติม
    parts.append("\n📙 ความทรงจำระยะยาว:")
    parts.append(WAIBON_MEMORY.strip())

    # กฎ
    parts.append("\n🚫 ข้อห้าม:")
    for item in WAIBON_RULES.get("rules", []):
        parts.append(f"- {item}")

    # โทนเสียง (จาก JSON)
    parts.append(f"\n🎯 โทนเสียงที่ต้องรักษา: {WAIBON_HEART['rules']['required_tone']}")
    
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
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": question}
                ]
            )
            response_text = response.choices[0].message.content
        except Exception as e:
            response_text = f"เกิดข้อผิดพลาด: {str(e)}"
    return render_template("index.html", response=response_text)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
