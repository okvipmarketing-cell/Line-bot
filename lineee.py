import os
import sqlite3
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi("zC1XczgR3zSaFD4wdms2ZSit+5jcxebiwOSDwMwNsYQE2dIEvku3qjWtmmCs1sx+iIz8DfvfMQj/fVy1O7fxNoBRdTpFQXTTXgcmtfeXsm0VQqxXoBmQ83yhVjZD6T25xuMWDpBvTHTUBPxGyueiiAdB04t89/1O/w1cDnyilFU=")
handler = WebhookHandler("dcd96b6b8d8659d088ae1e5c216c633b")

app = Flask(_name_)

DB_PATH = "groups.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

def save_group_id(group_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        INSERT INTO groups(group_id) VALUES(?)
        ON CONFLICT(group_id) DO UPDATE SET updated_at=CURRENT_TIMESTAMP
        """, (group_id,))

def list_group_ids():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT group_id FROM groups").fetchall()
    return [r[0] for r in rows]

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# 1) ตอนบอทถูกเชิญเข้ากลุ่ม จะมี JoinEvent (บางกรณี)
@handler.add(JoinEvent)
def handle_join(event):
    # event.source.group_id จะมีใน group
    if hasattr(event.source, "group_id") and event.source.group_id:
        save_group_id(event.source.group_id)

# 2) ตอนมีคนพิมพ์ในกลุ่ม เราจะเก็บ groupId ได้แน่นอน
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    src = event.source

    # เก็บ group_id ถ้ามาจากกลุ่ม
    if hasattr(src, "group_id") and src.group_id:
        save_group_id(src.group_id)

        # คำสั่งแอดมินง่ายๆ: พิมพ์ "register"
        if event.message.text.strip().lower() == "lineokvip":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="บันทึกกลุ่มเรียบร้อย ✅")
            )
            return

        # คำสั่ง broadcast จากในแชท (ตัวอย่าง)
        if event.message.text.startswith("sendall "):
            msg = event.message.text[len("sendall "):].strip()
            send_to_all_groups(msg)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"ส่งไปทุกกลุ่มที่บันทึกไว้แล้ว ✅")
            )
            return

    # ถ้าไม่ใช่กลุ่ม ก็ทำอย่างอื่นได้ (ข้ามไปก่อน)

def send_to_all_groups(text: str):
    group_ids = list_group_ids()
    for gid in group_ids:
        # push_message ส่งไป groupId ได้ ถ้าบอทอยู่ในกลุ่มนั้น
        line_bot_api.push_message(gid, TextSendMessage(text=text))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
