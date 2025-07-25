import os
import json
import re
import random
from datetime import datetime
from flask import Flask, render_template, request, session, send_file, redirect
from datetime import datetime, timedelta
import openai
import requests 
import waibon_adaptive_memory
import humanize
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
load_dotenv()

from waibon_gpt4o_switcher import waibon_ask

app = Flask(__name__)

@app.before_request
def block_line_inapp():
    user_agent = request.headers.get("User-Agent", "")
    path = request.path

    # ถ้ามาจาก LINE และไม่ได้เข้าหน้าแนะนำอยู่แล้ว
    if "Line" in user_agent and not path.startswith("/open-in-browser-guide"):
        return redirect("/open-in-browser-guide")
        
# app.secret_key = "waibon-secret-key"
app.secret_key = os.getenv("SECRET_KEY", "default_secret")

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

    if "@llama" in lowered:
        return "llama3-70b-8192"
    elif "@4o" in lowered:
        return "gpt-4o"
    elif "@3.5" in lowered:
        return "gpt-3.5-turbo"

    if any(word in lowered for word in [
        "วิเคราะห์", "เหตุผล", "เพราะอะไร", "เจตนา", 
        "อธิบาย", "เปรียบเทียบ", "ลึกซึ้ง", 
        "กลยุทธ์", "วางแผน", "ซับซ้อน"
    ]):
        return "gpt-4o"
    elif len(lowered.split()) > 30:
        return "gpt-4o"
    else:
        return os.getenv("OPENAI_MODEL", "llama3-70b-8192")

def call_groq(model, messages):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('LLAMA_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()


def parse_model_selector(message: str):
    message = message.strip()
    
    if message.startswith("@llama"):
        return "llama3-70b-8192", message.replace("@llama", "", 1).strip()
    elif message.startswith("@3.5"):
        return "gpt-3.5-turbo", message.replace("@3.5", "", 1).strip()
    elif message.startswith("@4o"):
        return "gpt-4o", message.replace("@4o", "", 1).strip()
    elif message.startswith("@4"):
        return "gpt-4", message.replace("@4", "", 1).strip()
    else:
        return None, message.strip()

def switch_model_and_provider(model_name: str):
    if "llama" in model_name:
        openai.api_key = os.getenv("LLAMA_API_KEY")
        # ✅ ปรับ fallback ให้ไม่มี /v1
        openai.base_url = os.getenv("LLAMA_BASE_URL", "https://api.groq.com/openai").rstrip("/")
    else:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        openai.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


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

def get_model_display_name(name: str) -> str:
    if "llama" in name:
        return "LLaMA 3"
    elif "gpt-4o" in name:
        return "GPT-4o"
    elif "gpt-3.5" in name:
        return "GPT-3.5"
    else:
        return name

def clean_reply(text, tone="neutral", model_used="gpt-4o", mode="default"):
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
    
    # 🔒 ถ้าใช้ GPT-3.5 ให้แทนคำให้สุภาพแบบผู้ชาย
    if model_used == "gpt-3.5-turbo":
        text = text.replace("ค่ะ", "ค่ะพี่สอง") \
                   .replace("คะ", "นะคะพี่สอง") \
                   .replace("ฉัน", "หนู๋") \
                   .replace("ดิฉัน", "หนู๋คิดว่า")
    
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

def call_groq(model, messages):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('LLAMA_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

@app.route("/", methods=["GET", "POST"])
def index():
    remaining = "∞"
    warning = None

    if request.method == "POST":
        question = request.form["question"]
        tone = "neutral"

        # ✅ NEW: ถ้าขึ้นต้นด้วย @ ให้วิ่งไป waibon_ask()
        if question.strip().startswith("@"):
            from waibon_gpt4o_switcher import waibon_ask
            reply = waibon_ask(question.strip())
            now_str = datetime.now().strftime("%d/%m/%y-%H:%M:%S")

            # ✅ บันทึกประวัติ
            if "chat_log" not in session:
                session["chat_log"] = []

            session["chat_log"].append({
                "question": question,
                "answer": reply,
                "ask_time": now_str,
                "reply_time": now_str,
                "model": "auto"  # หรือจะดึงจาก waibon_ask() ก็ได้ถ้าต้องการละเอียด
            })

            return render_template("index.html",
                response=reply,
                tone=tone,
                timestamp=now_str,
                remaining="∞",
                warning=None,
                model_used="auto"
            )
                
        if "@llama" in question:
            model_pref = "llama3-70b-8192"
        elif "@4o" in question:
            model_pref = "gpt-4o"
        elif "@3.5" in question:
            model_pref = "gpt-3.5-turbo"
        else:
            model_pref = None

        question = question.replace("@llama", "").replace("@4o", "").replace("@3.5", "").strip()
        file = request.files.get("file")

        messages = [{"role": "system", "content": "คุณคือผู้ช่วยชื่อไวบอน"}]
        if "chat_log" in session:
            for entry in session["chat_log"]:
                messages.append({"role": "user", "content": entry["question"]})
                messages.append({"role": "assistant", "content": entry["answer"]})
        messages.append({"role": "user", "content": question})

        try:
            model_used = model_pref or choose_model_by_question(question)
            switch_model_and_provider(model_used)

            if "llama" in model_used:
                # ใช้ Groq API โดยตรง
                response_json = call_groq(model_used, messages)
                reply = response_json["choices"][0]["message"]["content"].strip()
            else:
                # ใช้ OpenAI API ปกติ
                response = openai.chat.completions.create(
                    model=model_used,
                    messages=messages
                )
                reply = response.choices[0].message.content.strip() if response.choices else "..."

            model_label = get_model_display_name(model_used)
            reply = f"(โมเดล: {model_label})\n\n{reply}"

            now_str = datetime.now().strftime("%d/%m/%y-%H:%M:%S")

            if "chat_log" not in session:
                session["chat_log"] = []

            session["chat_log"].append({
                "question": question,
                "answer": reply,
                "file": file.filename if file and file.filename else None,
                "ask_time": now_str,
                "reply_time": now_str,
                "model": model_label
            })

            return render_template("index.html",
                response=reply,
                tone=tone,
                timestamp=now_str,
                remaining=remaining,
                warning=warning,
                model_used=model_used
            )

        except Exception as e:
            return f"❌ ERROR: {str(e)}"


    return render_template("index.html",
        tone="neutral",
        remaining=remaining,
        warning=warning
    )

    return render_template("index.html",
        response=response_text,
        tone=tone,
        timestamp=datetime.now().strftime("%H:%M:%S"),
        remaining=remaining,
        warning=warning,
        model_used=model_used
    )
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

@app.route("/open-in-browser-guide")
def open_in_browser_guide():
    return '''
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <title>โปรดเปิดในเบราว์เซอร์</title>
        <script>
            const isAndroid = /Android/i.test(navigator.userAgent);
            const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
            window.onload = () => {
                if (isAndroid) {
                    document.getElementById("android-btn").style.display = "block";
                } else if (isIOS) {
                    document.getElementById("ios-instruction").style.display = "block";
                }
            }
        </script>
    </head>
    <body style="font-family:sans-serif; padding:20px; text-align:center;">
        <h2>🚫 ระบบไม่รองรับการเปิดจากใน LINE</h2>
        <p>กรุณาเปิดในเบราว์เซอร์ปกติเพื่อใช้งานฟีเจอร์เต็ม</p>

        <!-- ปุ่ม Android -->
        <a id="android-btn"
           href="intent://waibon.onrender.com#Intent;scheme=https;package=com.android.chrome;end"
           style="display:none; padding:12px 24px; background-color:#4285f4; color:white; border-radius:8px; text-decoration:none; font-size:16px;">
           🚀 เปิดเว็บไซต์หลักใน Google Chrome
        </a>

        <!-- คำแนะนำสำหรับ iPhone -->
        <div id="ios-instruction" style="display:none; margin-top:20px; font-size:16px;">
            <p>📱 สำหรับผู้ใช้ iPhone:</p>
            <ul style="text-align:left; display:inline-block;">
                <li>แตะปุ่ม <strong>แชร์</strong> ที่มุมล่างขวา</li>
                <li>เลือก <strong>“เปิดใน Safari”</strong></li>
                <li>หากไม่มี Safari ให้คัดลอกลิงก์แล้วเปิดเอง</li>
            </ul>
            <p style="color:gray;">หรือเปิดลิงก์นี้: <br><code>https://waibon.onrender.com</code></p>
        </div>
    </body>
    </html>
    </html>
    '''

UPLOAD_DIR = "uploads"

@app.route("/ask_files", methods=["POST"])
@require_auth
def ask_with_files():
    question = request.form.get("question", "").strip()
    uploaded_files = request.files.getlist("newfile")

    saved_paths = []
    for file in uploaded_files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join("uploads", filename)
            file.save(filepath)
            saved_paths.append(filepath)

    combined_text = waibon_analyze(question, saved_paths)

    system_msg = build_personality_message()
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": combined_text}
    ]

    model_used = choose_model_by_question(combined_text)
    switch_model_and_provider(model_used)  # ✅ เพิ่มบรรทัดนี้

    response = openai.chat.completions.create(
        model=model_used,
        messages=messages
    )
    answer_text = response.choices[0].message.content.strip() if response.choices else "น้องขอเวลาคิดแป๊บนึงนะครับพี่สอง 🤔"

    model_label = get_model_display_name(model_used)  # ✅ เพิ่มตรงนี้

    if "chat_log" not in session:
        session["chat_log"] = []

    session["chat_log"].append({
        "question": combined_text,
        "answer": answer_text
    })

    return render_template("index.html",
        response=answer_text,
        tone="🎯 Files + Question",
        model_used=model_label,  # ✅ ใช้ตรงนี้แทน
        timestamp=datetime.now().strftime("%H:%M:%S"),
        remaining='∞',
        warning=False
    )

def get_file_info(filename):
    path = os.path.join(UPLOAD_DIR, filename)
    size = humanize.naturalsize(os.path.getsize(path))
    date = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".wav", ".mp3"]:
        group = "🎵 ไฟล์เสียง"
        ftype = "Audio"
    elif ext in [".zip"]:
        group = "📦 ZIP Archive"
        ftype = "ZIP"
    elif ext in [".tsv", ".jsonl", ".txt"]:
        group = "📄 ตาราง / ข้อความ"
        ftype = "Text"
    else:
        group = "🗃️ อื่น ๆ"
        ftype = "Unknown"

    return {
        "name": filename,
        "size": size,
        "date": date,
        "group": group,
        "type": ftype
    }

@app.route("/upload-panel")
@require_auth
def upload_panel():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    files = [get_file_info(f) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
    grouped = {}
    for f in files:
        grouped.setdefault(f["group"], []).append(f)
    return render_template("upload_panel.html", grouped_files=grouped)

@app.route("/upload_file", methods=["POST"])
@require_auth
def upload_file():
    files = request.files.getlist("newfile")
    if not files:
        return "❌ ไม่พบไฟล์"

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    for file in files:
        if file.filename == "":
            continue  # ข้ามไฟล์ว่าง
        filepath = os.path.join(UPLOAD_DIR, file.filename)
        file.save(filepath)

    return redirect("/upload-panel")


@app.route("/analyze_selected", methods=["POST"])
@require_auth
def analyze_selected():
    selected = request.form.getlist("selected_files")
    if not selected:
        return redirect("/upload-panel")  # กลับไปหน้าเดิม

    messages = []
    for fname in selected:
        path = os.path.join(UPLOAD_DIR, fname)
        # วิเคราะห์แบบเบา ๆ (หรือจริงจังก็ได้)
        messages.append(f"🔍 วิเคราะห์ไฟล์: {fname}")

    # Render กลับหน้าเดิม พร้อมข้อความ
    files = [get_file_info(f) for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
    grouped = {}
    for f in files:
        grouped.setdefault(f["group"], []).append(f)

    return render_template("upload_panel.html", grouped_files=grouped, analyze_results=messages)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
