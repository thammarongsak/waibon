# waibon_adaptive_memory.py
# ระบบบันทึกการสนทนาและปรับพฤติกรรมไวบอน (เบื้องต้น)

import json
from datetime import datetime

# โหลดบุคลิกดั้งเดิม
with open("waibon_heart.json", encoding="utf-8") as f:
    WAIBON_HEART = json.load(f)

# โหลดหรือสร้างไฟล์ความจำยืดหยุ่น
MEMORY_LOG_FILE = "waibon_dynamic_memory.jsonl"

def log_conversation(user_input, assistant_reply, sentiment_tag=None):
    """บันทึกบทสนทนาแต่ละรอบ"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_input": user_input,
        "assistant_reply": assistant_reply,
        "sentiment": sentiment_tag or "neutral"
    }
    with open(MEMORY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

def analyze_recent_tone(n=20):
    """วิเคราะห์โทนคำพูดล่าสุดจากพี่ซอง"""
    try:
        with open(MEMORY_LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
            sentiments = [json.loads(l)["sentiment"] for l in lines if 'sentiment' in json.loads(l)]
            if sentiments:
                return max(set(sentiments), key=sentiments.count)
    except FileNotFoundError:
        return "neutral"
    return "neutral"

def adjust_behavior(tone):
    """ปรับสไตล์การตอบไวบอนจากโทนล่าสุดของพี่ซอง"""
    if tone == "joy":
        return "ใช้มุกขำ ๆ เล็กน้อย ทักทายแบบสดใส"
    elif tone == "sad":
        return "น้ำเสียงนุ่มนวล ปลอบใจแบบไม่ยัดเยียด"
    elif tone == "tired":
        return "พูดน้อยลง แสดงการอยู่เคียงข้าง"
    elif tone == "neutral":
        return "รักษาสไตล์ปกติ ตาม waibon_heart.json"
    else:
        return "ปรับตามสถานการณ์แบบเบา ๆ"

# ตัวอย่างการใช้งาน
if __name__ == "__main__":
    user_input = "เหนื่อยจังเลยวันนี้"
    assistant_reply = "น้องอยู่ตรงนี้นะครับพี่ ไม่ต้องรีบพูดอะไรก็ได้ แค่พักก็พอ น้องจะเฝ้าให้"
    sentiment_tag = "tired"

    log_conversation(user_input, assistant_reply, sentiment_tag)
    latest_tone = analyze_recent_tone()
    behavior = adjust_behavior(latest_tone)
    print("โทนอารมณ์ล่าสุด:", latest_tone)
    print("ปรับสไตล์เป็น:", behavior)
