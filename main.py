from flask import Flask, request, render_template, session, redirect, send_file
from datetime import datetime, timedelta
import os, json
from werkzeug.utils import secure_filename
import openai

# === ตั้งค่าแอป ===
import re
import random
import waibon_adaptive_memory
import humanize
app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.permanent_session_lifetime = timedelta(days=365)
UPLOAD_FOLDER = "uploads"
LOG_FILE = "chat_log.jsonl"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === ฟังก์ชันเลือกโมเดล ===
def choose_model(prompt):
    if "@4o" in prompt:
        return "gpt-4o"
    elif "@3.5" in prompt:
        return "gpt-3.5-turbo"
    elif any(x in prompt for x in ["วิเคราะห์", "เหตุผล", "เพราะอะไร", "เจตนา", "อธิบาย", "เปรียบเทียบ", "ลึกซึ้ง", "กลยุทธ์", "วางแผน", "ซับซ้อน"]):
        return "gpt-4o"
    return "gpt-3.5-turbo"

# === โหลดโหมดคาแรกเตอร์ ===
with open("waibon_heart_unified.json", encoding="utf-8") as f:
    heart = json.load(f)

# === โหลดข้อมูลไวบอนทั้งหมด ===
with open("waibon_heart_unified.json", encoding="utf-8") as f:
    WAIBON_STATIC = json.load(f)

# === โหมดคาแรกเตอร์ ===
PERSONALITY_MODES = WAIBON_STATIC.get("modes", {})

# === ฟังก์ชันล้าง/จัดการคำตอบ ===
def sanitize_user_input(text):
    banned = ["ฆ่า", "ตาย", "ด่าพ่อ", "เผาบ้าน"]
    for b in banned:
        text = text.replace(b, "*")
    return text

def clean_reply(text):
    for word in ["สุดยอด", "พรสวรรค์", "เทพเจ้า"]:
        text = text.replace(word, "")
    return text

def log_conversation(chat_item):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(chat_item, ensure_ascii=False) + "\n")

# === ประเมินโมเดลจากคำถาม ===
def parse_model_selector(question):
    return "gpt-4o" if "@4o" in question else ("gpt-3.5-turbo" if "@3.5" in question else None)

# === LINE Blocker ===
@app.before_request
def block_line_inapp():
    user_agent = request.headers.get("User-Agent", "")
    path = request.path
    if "Line" in user_agent and not path.startswith("/open-in-browser-guide"):
        return redirect("/open-in-browser-guide")
tone = heart.get("rules", {}).get("required_tone", "อบอุ่น")

# === Route หลัก ===
@app.route("/", methods=["GET", "POST"])
def index():
    if "chat_log" not in session:
        session["chat_log"] = []
    session.permanent = True
    warning = None
    remaining = "∞"

    if request.method == "POST":
        question = request.form["question"]
        file = request.files.get("file")
        filename = None

        # จัดการไฟล์แนบ
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))

        # เลือกโมเดล
        model_used = choose_model(question)
        clean_prompt = question.replace("@3.5", "").replace("@4o", "").strip()

        try:
            response = openai.ChatCompletion.create(
                model=model_used,
                messages=[{"role": "user", "content": clean_prompt}]
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            reply = "เกิดข้อผิดพลาด: {}".format(e)

        now_str = datetime.now().strftime("%d/%m/%y-%H:%M:%S")
        chat_item = {
            "question": question,
            "answer": reply,
            "file": filename,
            "ask_time": now_str,
            "reply_time": now_str,
            "model": "GPT-4o" if "4o" in model_used else "GPT-3.5"
        }
        session["chat_log"].append(chat_item)

        # log ลงไฟล์
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(chat_item, ensure_ascii=False) + "\n")

    return render_template("index.html", tone=tone, warning=warning, remaining=remaining)

# === Route สำหรับอัปโหลดไฟล์เพิ่มเติม ===
@app.route("/upload-panel", methods=["GET"])
def upload_panel():
    grouped = {"อัปโหลดล่าสุด": []}
    for fname in os.listdir(UPLOAD_FOLDER):
        fpath = os.path.join(UPLOAD_FOLDER, fname)
        if os.path.isfile(fpath):
            grouped["อัปโหลดล่าสุด"].append({
                "name": fname,
                "type": fname.split(".")[-1],
                "size": os.path.getsize(fpath),
                "date": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
            })
    return render_template("upload_panel.html", grouped_files=grouped)

# === ล้างบทสนทนา ===
@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    session["chat_log"] = []
    return redirect("/")

# === ดาวน์โหลด log ===
@app.route("/download_log/<format>")
def download_log(format):
    if format == "txt":
        content = ""
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                content += f"ถาม: {item['question']}\nตอบ: {item['answer']}\n---\n"
        with open("log.txt", "w", encoding="utf-8") as out:
            out.write(content)
        return send_file("log.txt", as_attachment=True)
    elif format == "jsonl":
        return send_file(LOG_FILE, as_attachment=True)
    return "ไม่รองรับฟอร์แมตนี้", 400

if __name__ == "__main__":
    app.run(debug=True)
