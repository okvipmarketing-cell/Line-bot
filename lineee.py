import os
import sqlite3
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent

# ===== CONFIG (ENV only) =====
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET in env.")

line_bot_api = LineBotApi("hh8diWyijb6Z17Yjlr5yN5jeT3M5VGGqj5mXsJK4ELLb2QGlGkR99VtiwlLM3TA/iIz8DfvfMQj/fVy1O7fxNoBRdTpFQXTTXgcmtfeXsm0LE3PFCtGpfXpsAmOKT/+9a07ABnoqfGzcIpuU1qqmqgdB04t89/1O/w1cDnyilFU=")
handler = WebhookHandler("fc551ae7c642a0046b7b4e1cab7b569c")

app = Flask(__name__)
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

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/callback", methods=["GET", "POST"])
def callback():
    if request.method == "GET":
        return "callback alive", 200

    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    print("=== WEBHOOK IN ===")
    print(body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("InvalidSignatureError: secret ไม่ตรง หรือคนละ channel")
        abort(400)
    except Exception as e:
        print("Unexpected error:", repr(e))
        abort(500)

    return "OK", 200

@handler.add(JoinEvent)
def handle_join(event):
    if hasattr(event.source, "group_id") and event.source.group_id:
        gid = event.source.group_id
        save_group_id(gid)
        print("Saved group_id from JoinEvent:", gid)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = (event.message.text or "").strip()
    src = event.source

    # group chat
    if hasattr(src, "group_id") and src.group_id:
        gid = src.group_id
        save_group_id(gid)
        print("Saved group_id from MessageEvent:", gid)

        if text.lower() == "lineokvip":
            try:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="บันทึกกลุ่มเรียบร้อย ✅")
                )
            except LineBotApiError as e:
                print("Reply error:", e.status_code, e.error.message)
            return

        if text.lower().startswith("sendall "):
            msg = text[len("sendall "):].strip()
            send_to_all_groups(msg)
            try:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="ส่งไปทุกกลุ่มที่บันทึกไว้แล้ว ✅")
                )
            except LineBotApiError as e:
                print("Reply error:", e.status_code, e.error.message)
            return

        # เทสให้รู้ว่าบอทตอบได้จริง
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"รับข้อความแล้ว ✅: {text}")
            )
        except LineBotApiError as e:
            print("Reply error:", e.status_code, e.error.message)
        return

    # private chat
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="บอทออนไลน์แล้ว ✅\nเชิญเข้ากลุ่ม แล้วพิมพ์: lineokvip")
        )
    except LineBotApiError as e:
        print("Reply error:", e.status_code, e.error.message)

def send_to_all_groups(text: str):
    group_ids = list_group_ids()
    print("Broadcast groups:", group_ids)
    for gid in group_ids:
        try:
            line_bot_api.push_message(gid, TextSendMessage(text=text))
        except LineBotApiError as e:
            print("Push error:", gid, e.status_code, e.error.message)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
