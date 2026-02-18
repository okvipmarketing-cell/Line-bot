import os
import sqlite3
import time
from dotenv import load_dotenv
from flask import Flask, request, abort, jsonify, render_template_string

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    JoinEvent
)

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
ADMIN_USER = os.getenv("ADMIN_USER", "")      # optional (เพิ่มความปลอดภัย)
ADMIN_PASS = os.getenv("ADMIN_PASS", "")      # optional (เพิ่มความปลอดภัย)

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError("กรุณาตั้งค่า LINE_CHANNEL_ACCESS_TOKEN และ LINE_CHANNEL_SECRET ใน .env")

line_bot_api = LineBotApi("hh8diWyijb6Z17Yjlr5yN5jeT3M5VGGqj5mXsJK4ELLb2QGlGkR99VtiwlLM3TA/iIz8DfvfMQj/fVy1O7fxNoBRdTpFQXTTXgcmtfeXsm0LE3PFCtGpfXpsAmOKT/+9a07ABnoqfGzcIpuU1qqmqgdB04t89/1O/w1cDnyilFU=")
handler = WebhookHandler("fc551ae7c642a0046b7b4e1cab7b569c")

app = Flask(__name__)
DB_PATH = "groups.db"


# -------------------------
# Database: เก็บ groupId
# -------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS send_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            message TEXT,
            total_groups INTEGER,
            success_count INTEGER,
            fail_count INTEGER
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
        rows = conn.execute("SELECT group_id FROM groups ORDER BY updated_at DESC").fetchall()
    return [r[0] for r in rows]

def insert_log(message: str, total: int, ok: int, fail: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        INSERT INTO send_logs(message, total_groups, success_count, fail_count)
        VALUES(?, ?, ?, ?)
        """, (message, total, ok, fail))

def recent_logs(limit: int = 20):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
        SELECT sent_at, message, total_groups, success_count, fail_count
        FROM send_logs
        ORDER BY id DESC
        LIMIT ?
        """, (limit,)).fetchall()
    return rows


# -------------------------
# Simple Auth (optional)
# -------------------------
def check_admin_auth(req):
    """
    เลือกได้ 2 ชั้น:
    1) ADMIN_KEY (บังคับ)
    2) Basic Auth (ถ้าตั้ง ADMIN_USER/ADMIN_PASS)
    """
    # ชั้นที่ 2 (ถ้าตั้ง)
    if ADMIN_USER and ADMIN_PASS:
        auth = req.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return False
    return True


# -------------------------
# Webhook endpoint
# -------------------------
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(JoinEvent)
def handle_join(event):
    # เมื่อบอทเข้ากลุ่ม
    if hasattr(event.source, "group_id") and event.source.group_id:
        save_group_id(event.source.group_id)


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # เมื่อมีคนพิมพ์ในกลุ่ม -> เก็บ group_id ได้แน่นอน
    src = event.source
    if hasattr(src, "group_id") and src.group_id:
        save_group_id(src.group_id)

        # คำสั่ง register (ไม่จำเป็นแต่ช่วยให้ทีมรู้ว่าเก็บแล้ว)
        if event.message.text.strip().lower() == "OKVIP":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="บันทึกกลุ่มเรียบร้อย ✅")
            )


# -------------------------
# Admin UI
# -------------------------
ADMIN_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>LINE Broadcast Admin</title>
  <style>
    body { font-family: Arial; max-width: 860px; margin: 40px auto; padding: 0 14px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    textarea { width: 100%; height: 160px; font-size: 16px; padding: 10px; border-radius: 10px; border: 1px solid #ccc; }
    input { width: 100%; font-size: 16px; padding: 10px; border-radius: 10px; border: 1px solid #ccc; }
    button { font-size: 16px; padding: 10px 16px; cursor: pointer; border-radius: 10px; border: 1px solid #333; background: #fff; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .hint { color: #666; font-size: 13px; margin: 6px 0; }
    .ok { color: #0a7; }
    .bad { color: #c33; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #eee; padding: 8px; text-align: left; font-size: 14px; }
  </style>
</head>
<body>
  <h2>Broadcast ไปทุกกลุ่ม</h2>

  <div class="card">
    <div class="row">
      <div>
        <div class="hint">Admin Key (ต้องใส่)</div>
        <input id="key" placeholder="ADMIN_KEY" type="password"/>
      </div>
      <div>
        <div class="hint">หน่วงเวลา/กลุ่ม (ms) (กันชน rate limit)</div>
        <input id="delay" placeholder="เช่น 200" value="200"/>
      </div>
    </div>

    <div class="hint" style="margin-top:12px;">ข้อความที่จะส่ง</div>
    <textarea id="msg" placeholder="พิมพ์ข้อความประกาศ..."></textarea>

    <div style="margin-top:12px; display:flex; gap:10px; align-items:center;">
      <button onclick="send()">ส่งข้อความ</button>
      <span id="status"></span>
    </div>

    <div class="hint" style="margin-top:10px;">
      หมายเหตุ: ส่งได้เฉพาะกลุ่มที่บอทอยู่ในกลุ่มนั้น และ groupId ถูกบันทึกไว้แล้ว (พิมพ์ register ในกลุ่ม 1 ครั้ง)
    </div>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">สถานะกลุ่ม</h3>
    <button onclick="refreshGroups()">รีเฟรชรายการกลุ่ม</button>
    <p class="hint" id="groupInfo"></p>
    <pre id="groups" style="white-space:pre-wrap;"></pre>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">ประวัติการส่งล่าสุด</h3>
    <button onclick="refreshLogs()">รีเฟรช Log</button>
    <div id="logs"></div>
  </div>

<script>
async function send(){
  const key = document.getElementById('key').value.trim();
  const msg = document.getElementById('msg').value.trim();
  const delay = parseInt(document.getElementById('delay').value || "0", 10);

  const status = document.getElementById('status');
  status.className = '';
  status.textContent = 'กำลังส่ง...';

  const res = await fetch('/admin/send', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ key, msg, delay_ms: delay })
  });

  const data = await res.json().catch(()=>({}));

  if(res.ok){
    status.className = 'ok';
    status.textContent = `ส่งสำเร็จ ✅ ทั้งหมด ${data.total_groups} กลุ่ม | สำเร็จ ${data.success} | ล้มเหลว ${data.fail}`;
    await refreshLogs();
  }else{
    status.className = 'bad';
    status.textContent = `ส่งไม่สำเร็จ ❌ ${data.error || 'unknown error'}`;
  }
}

async function refreshGroups(){
  const key = document.getElementById('key').value.trim();
  const res = await fetch('/admin/groups?key=' + encodeURIComponent(key));
  const data = await res.json().catch(()=>({}));
  const info = document.getElementById('groupInfo');
  const box = document.getElementById('groups');

  if(res.ok){
    info.textContent = `จำนวนกลุ่มที่บันทึกไว้: ${data.count}`;
    box.textContent = data.groups.join('\\n');
  }else{
    info.textContent = '';
    box.textContent = data.error || 'error';
  }
}

async function refreshLogs(){
  const key = document.getElementById('key').value.trim();
  const res = await fetch('/admin/logs?key=' + encodeURIComponent(key));
  const data = await res.json().catch(()=>({}));

  const wrap = document.getElementById('logs');
  if(!res.ok){
    wrap.innerHTML = '<div class="bad">' + (data.error || 'error') + '</div>';
    return;
  }

  let html = '<table><thead><tr><th>เวลา</th><th>ข้อความ</th><th>รวม</th><th>สำเร็จ</th><th>ล้มเหลว</th></tr></thead><tbody>';
  for(const r of data.logs){
    html += `<tr>
      <td>${r.sent_at}</td>
      <td>${escapeHtml(r.message)}</td>
      <td>${r.total_groups}</td>
      <td>${r.success_count}</td>
      <td>${r.fail_count}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function escapeHtml(s){
  return (s||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
}

refreshLogs();
</script>

</body>
</html>
"""

@app.route("/admin", methods=["GET"])
def admin_page():
    if not check_admin_auth(request):
        return abort(401)
    return render_template_string(ADMIN_HTML)


def require_admin_key(key: str):
    if not ADMIN_KEY:
        return False
    return (key or "").strip() == ADMIN_KEY


@app.route("/admin/groups", methods=["GET"])
def admin_groups():
    if not check_admin_auth(request):
        return abort(401)

    key = request.args.get("key", "")
    if not require_admin_key(key):
        return jsonify({"error": "Admin key ไม่ถูกต้อง"}), 401

    groups = list_group_ids()
    return jsonify({"count": len(groups), "groups": groups})


@app.route("/admin/logs", methods=["GET"])
def admin_logs():
    if not check_admin_auth(request):
        return abort(401)

    key = request.args.get("key", "")
    if not require_admin_key(key):
        return jsonify({"error": "Admin key ไม่ถูกต้อง"}), 401

    logs = recent_logs(20)
    return jsonify({
        "logs": [
            {
                "sent_at": r[0],
                "message": r[1],
                "total_groups": r[2],
                "success_count": r[3],
                "fail_count": r[4],
            } for r in logs
        ]
    })


@app.route("/admin/send", methods=["POST"])
def admin_send():
    if not check_admin_auth(request):
        return abort(401)

    payload = request.get_json(silent=True) or {}
    key = (payload.get("key") or "").strip()
    msg = (payload.get("msg") or "").strip()
    delay_ms = int(payload.get("delay_ms") or 0)

    if not require_admin_key(key):
        return jsonify({"error": "Admin key ไม่ถูกต้อง"}), 401
    if not msg:
        return jsonify({"error": "ข้อความว่าง"}), 400

    group_ids = list_group_ids()
    total = len(group_ids)

    success = 0
    fail = 0

    for gid in group_ids:
        try:
            line_bot_api.push_message(gid, TextSendMessage(text=msg))
            success += 1
        except LineBotApiError:
            fail += 1

        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    insert_log(msg, total, success, fail)

    return jsonify({
        "ok": True,
        "total_groups": total,
        "success": success,
        "fail": fail
    })


@app.route("/", methods=["GET"])
def health():
    return "OK"


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000)
