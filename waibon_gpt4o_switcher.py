# waibon_gpt4o_switcher.py
import os
import openai
from dotenv import load_dotenv

# โหลด API Key จาก .env (หรือกำหนดตรงนี้ก็ได้)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ค่าโมเดลปัจจุบัน
current_model = "llama-3"

def switch_model(model_name):
    global current_model
    if model_name in ["llama-3", "gpt-4o"]:
        current_model = model_name
        return f"✅ เปลี่ยนโมเดลเป็น: {current_model}"
    else:
        return f"❌ ไม่รู้จักโมเดล '{model_name}'"

def get_model_status():
    return f"📍 โมเดลปัจจุบันคือ: {current_model}"

def ask_llama(prompt):
    # จำลองคำตอบ LLaMA (ในระบบจริงให้เชื่อม Groq หรือ Ollama แทน)
    return f"[LLaMA] ตอบกลับ: {prompt}", "llama-3"

def ask_gpt4o(prompt):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are Waibon, beat analysis expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content, "gpt-4o"
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาด: {str(e)}", "error"

def waibon_ask(text):
    if text.startswith("@llama"):
        return ask_llama(text.replace("@llama", "", 1).strip())
    elif text.startswith("@gpt4o"):
        return ask_gpt4o(text.replace("@gpt4o", "", 1).strip())
    elif text.startswith("@status"):
        return get_model_status(), current_model
    elif text.startswith("@analyze"):
        topic = text.replace("@analyze", "").strip()
        return f"🔍 วิเคราะห์: {topic} ด้วยโมเดล {current_model}", current_model
    else:
        if current_model == "llama-3":
            return ask_llama(text)
        elif current_model == "gpt-4o":
            return ask_gpt4o(text)
        else:
            return "❌ ไม่รู้จักโมเดลที่กำลังใช้งานอยู่", "unknown"
