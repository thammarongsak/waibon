import os
import json
from flask import Flask, render_template, request
import openai

# โหลดบุคลิกไวบอนจากไฟล์ .json
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

# สร้างข้อความ personality จากข้อมูลใน JSON
def build_personality_message(data):
    parts = []
    parts.append(data["voice_style"])
    for item in data["memory"]:
        parts.append(item)
    parts.append("ข้อห้าม: " + " ".join(data["rules"]["forbidden"]))
    parts.append("น้ำเสียง: " + data["rules"]["required_tone"])
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
            system_msg = build_personality_message(WAIBON_HEART)
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
