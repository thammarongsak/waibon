from flask import Flask, render_template, request
import openai
import os
import json

# โหลดหัวใจไวบอนจากไฟล์ .json
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_PERSONALITY = json.load(f)

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/", methods=["GET", "POST"])
def index():
    response_text = ""
    if request.method == "POST":
        question = request.form["question"]
        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": json.dumps(WAIBON_PERSONALITY, ensure_ascii=False)},
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
