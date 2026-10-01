"""
WhatsApp Evolution API Bot with Secure Database, Full Chat Memory & CSV Storage
-------------------------------------------------------------------------------
Features:
1. Full Chat Memory: Stores every incoming and outgoing WhatsApp message in SQLite.
2. Secure Data Vault: Datasets are password-protected with salted SHA-256 hashes.
3. Flexible Data Capture:
   - Single message: !TakeInfo <data_name> <data_pass> <data...>
   - Multi-message mode: !TakeInfo <data_name> <data_pass> followed by data messages, then !done
4. Local Well-Formed CSV Export: Every dataset is cleanly saved to ./data/<data_name>.csv.
5. Interactive Guide: Comprehensive guidance via !help or !guide commands.
"""

import os
import csv
import json
import uuid
import hashlib
import secrets
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import requests
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------------
# Configuration & Environment Variables
# ---------------------------------------------------------------------------
EVOLUTION_API_URL = os.getenv(
    "EVOLUTION_API_URL", "http://evo-hcoka1lffshxmnxquji5smug.localhost.sslip.io"
).rstrip("/")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "xvOagvh8NKcj8mOZ7VQq0lCuaAyt92iu")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "Name")
PORT = int(os.getenv("PORT", "9000"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "memory.db")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Database Management (Full Chat Memory & Secure Dataset Registry)
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables for full chat memory, dataset registry, and sessions."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Full Chat Memory
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                remote_jid TEXT NOT NULL,
                sender_number TEXT NOT NULL,
                direction TEXT NOT NULL, -- 'incoming' or 'outgoing'
                message_id TEXT,
                content TEXT NOT NULL
            )
        """)
        
        # 2. Secure Datasets Registry
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                data_name TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                owner_number TEXT NOT NULL,
                created_at TEXT NOT NULL,
                csv_path TEXT NOT NULL
            )
        """)
        
        # 3. Active Multi-Message Sessions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                sender_number TEXT PRIMARY KEY,
                data_name TEXT NOT NULL,
                started_at TEXT NOT NULL
            )
        """)
        
        # 4. Ingested Data Records
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_records (
                record_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                data_name TEXT NOT NULL,
                sender_number TEXT NOT NULL,
                content TEXT NOT NULL,
                format_type TEXT NOT NULL
            )
        """)
        conn.commit()

init_db()

# ---------------------------------------------------------------------------
# Security Helpers (Salted Password Hashing)
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hashes password with SHA-256 and unique salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hashed, salt

def verify_dataset_access(data_name: str, password: str, sender_number: str) -> Tuple[bool, str]:
    """
    Verifies if the password matches the dataset.
    If the dataset doesn't exist, registers it securely.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt FROM datasets WHERE data_name = ?", (data_name,))
        row = cursor.fetchone()
        
        if row is None:
            # Register new dataset with this password
            pwd_hash, salt = hash_password(password)
            csv_path = os.path.join(DATA_DIR, f"{data_name}.csv")
            cursor.execute(
                "INSERT INTO datasets (data_name, password_hash, salt, owner_number, created_at, csv_path) VALUES (?, ?, ?, ?, ?, ?)",
                (data_name, pwd_hash, salt, sender_number, datetime.utcnow().isoformat(), csv_path)
            )
            conn.commit()
            return True, "created"
        
        # Verify existing dataset password
        stored_hash = row["password_hash"]
        salt = row["salt"]
        calc_hash, _ = hash_password(password, salt)
        if calc_hash == stored_hash:
            return True, "authorized"
        else:
            return False, "Invalid password for this dataset!"

# ---------------------------------------------------------------------------
# Evolution API Client
# ---------------------------------------------------------------------------
def send_whatsapp_message(recipient: str, text: str):
    """Sends a text message using Evolution API and saves to memory."""
    # Ensure recipient format (without @s.whatsapp.net suffix)
    clean_number = recipient.split("@")[0].strip()
    
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": clean_number,
        "text": text
    }
    
    # Save outgoing message in chat memory
    try:
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO chat_history (timestamp, remote_jid, sender_number, direction, message_id, content) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.utcnow().isoformat(), f"{clean_number}@s.whatsapp.net", clean_number, "outgoing", None, text)
            )
            conn.commit()
    except Exception as db_err:
        print(f"[DB Error] Outgoing chat memory: {db_err}")

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code not in (200, 201):
            print(f"[Evolution API Warning] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Evolution API Error] Failed to send message to {clean_number}: {e}")

# ---------------------------------------------------------------------------
# CSV Storage Engine
# ---------------------------------------------------------------------------
def detect_format(content: str) -> str:
    """Detects whether content is JSON, Key-Value pairs, CSV row, or free text."""
    content_stripped = content.strip()
    if (content_stripped.startswith("{") and content_stripped.endswith("}")) or \
       (content_stripped.startswith("[") and content_stripped.endswith("]")):
        try:
            json.loads(content_stripped)
            return "JSON"
        except Exception:
            pass
    if ":" in content and "\n" in content:
        return "KEY_VALUE_MULTILINE"
    if ":" in content and "," in content:
        return "KEY_VALUE_INLINE"
    if "," in content:
        return "CSV_ROW"
    return "FREE_TEXT"

def save_data_record(data_name: str, sender_number: str, content: str):
    """Stores record into SQLite and appends to local dataset CSV."""
    now_iso = datetime.utcnow().isoformat()
    record_id = str(uuid.uuid4())[:8]
    fmt = detect_format(content)
    
    # 1. SQLite Storage
    with get_db() as conn:
        conn.cursor().execute(
            "INSERT INTO data_records (record_id, timestamp, data_name, sender_number, content, format_type) VALUES (?, ?, ?, ?, ?, ?)",
            (record_id, now_iso, data_name, sender_number, content, fmt)
        )
        conn.commit()
        
    # 2. Local CSV Storage
    csv_file = os.path.join(DATA_DIR, f"{data_name}.csv")
    file_exists = os.path.exists(csv_file)
    
    fieldnames = ["record_id", "timestamp_utc", "data_name", "sender_number", "format_detected", "content"]
    with open(csv_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "record_id": record_id,
            "timestamp_utc": now_iso,
            "data_name": data_name,
            "sender_number": sender_number,
            "format_detected": fmt,
            "content": content
        })

# ---------------------------------------------------------------------------
# Command Handlers & Business Logic
# ---------------------------------------------------------------------------
GUIDE_TEXT = """📖 *SECURE DATA VAULT GUIDE* 📖

*1. Save Data in a Single Message:*
`!TakeInfo <data_name> <password> <your content>`
Example:
`!TakeInfo expenses pass123 Coffee: $4, Lunch: $12`
_Creates or appends to dataset 'expenses'._

*2. Multi-Message Data Ingestion:*
Start by typing:
`!TakeInfo <data_name> <password>`
Send each piece of data as separate messages!
When done, type:
`!done`  (or `!save`)
To abort, type: `!cancel`

*3. View Dataset Records:*
`!ViewInfo <data_name> <password>`

*4. Export / File Status:*
`!Export <data_name> <password>`
_Shows total records and file location on server._

*5. Chat Memory History:*
`!history`
_Shows recent recorded messages._

*Security Rules:*
- Passwords are salt-hashed.
- The first password used for `<data_name>` locks that dataset.
- Anyone appending or reading must provide that exact password.
"""

def handle_user_message(sender_number: str, message_text: str):
    text = message_text.strip()
    
    # 1. Check for active multi-message session
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data_name FROM active_sessions WHERE sender_number = ?", (sender_number,))
        session = cursor.fetchone()
        
    if session:
        data_name = session["data_name"]
        if text.lower() in ("!done", "!save"):
            with get_db() as conn:
                conn.cursor().execute("DELETE FROM active_sessions WHERE sender_number = ?", (sender_number,))
                conn.commit()
            send_whatsapp_message(
                sender_number,
                f"✅ Multi-message ingestion finished!\nDataset *{data_name}* updated and saved to local CSV."
            )
            return
        elif text.lower() == "!cancel":
            with get_db() as conn:
                conn.cursor().execute("DELETE FROM active_sessions WHERE sender_number = ?", (sender_number,))
                conn.commit()
            send_whatsapp_message(sender_number, f"❌ Multi-message session for *{data_name}* cancelled.")
            return
        else:
            # Ingest this message into the active dataset
            save_data_record(data_name, sender_number, text)
            send_whatsapp_message(
                sender_number,
                f"📥 Captured into *{data_name}*!\nSend more data, or send `!done` to finish."
            )
            return

    # 2. Guide / Help Command
    if text.lower() in ("!help", "!guide", "help", "guide"):
        send_whatsapp_message(sender_number, GUIDE_TEXT)
        return

    # 3. Handle !TakeInfo Command
    if text.startswith("!TakeInfo"):
        parts = text.split(maxsplit=3)
        if len(parts) < 3:
            send_whatsapp_message(
                sender_number,
                "⚠️ *Usage Error*\nSyntax: `!TakeInfo <data_name> <data_pass> [content]`\nType `!guide` for full details."
            )
            return
            
        data_name = parts[1].strip()
        data_pass = parts[2].strip()
        
        # Verify / authenticate password
        authorized, reason = verify_dataset_access(data_name, data_pass, sender_number)
        if not authorized:
            send_whatsapp_message(
                sender_number,
                f"🔒 *Access Denied!* {reason}\nPlease provide the correct password for dataset *{data_name}*."
            )
            return

        # Case A: Content provided in same message
        if len(parts) == 4 and parts[3].strip():
            inline_content = parts[3].strip()
            save_data_record(data_name, sender_number, inline_content)
            status_msg = "Created & saved" if reason == "created" else "Appended"
            send_whatsapp_message(
                sender_number,
                f"✅ *{status_msg} successfully!*\n📁 Dataset: `{data_name}`\n📄 Stored into CSV and Database."
            )
            return
        
        # Case B: Multi-message mode initiated
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO active_sessions (sender_number, data_name, started_at) VALUES (?, ?, ?)",
                (sender_number, data_name, datetime.utcnow().isoformat())
            )
            conn.commit()
            
        send_whatsapp_message(
            sender_number,
            f"📥 *Multi-message mode activated for '{data_name}'!*\n"
            f"Send any data in subsequent messages.\n"
            f"When finished, send `!done`.\n"
            f"To abort, send `!cancel`."
        )
        return

    # 4. Handle !ViewInfo Command
    if text.startswith("!ViewInfo"):
        parts = text.split()
        if len(parts) < 3:
            send_whatsapp_message(sender_number, "⚠️ Usage: `!ViewInfo <data_name> <data_pass>`")
            return
        data_name, data_pass = parts[1], parts[2]
        authorized, reason = verify_dataset_access(data_name, data_pass, sender_number)
        if not authorized or reason == "created":
            send_whatsapp_message(sender_number, f"🔒 *Access Denied* or dataset doesn't exist.")
            return
            
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp, content FROM data_records WHERE data_name = ? ORDER BY timestamp DESC LIMIT 5",
                (data_name,)
            )
            rows = cursor.fetchall()
            
        if not rows:
            send_whatsapp_message(sender_number, f"ℹ️ Dataset *{data_name}* has no records yet.")
            return
            
        msg = f"📊 *Recent records for '{data_name}':*\n"
        for idx, r in enumerate(reversed(rows), 1):
            msg += f"\n[{idx}] ({r['timestamp'][:19]}):\n{r['content']}\n"
        send_whatsapp_message(sender_number, msg)
        return

    # 5. Handle !Export Command
    if text.startswith("!Export"):
        parts = text.split()
        if len(parts) < 3:
            send_whatsapp_message(sender_number, "⚠️ Usage: `!Export <data_name> <data_pass>`")
            return
        data_name, data_pass = parts[1], parts[2]
        authorized, reason = verify_dataset_access(data_name, data_pass, sender_number)
        if not authorized or reason == "created":
            send_whatsapp_message(sender_number, f"🔒 *Access Denied* or dataset doesn't exist.")
            return
            
        csv_file = os.path.join(DATA_DIR, f"{data_name}.csv")
        row_count = 0
        if os.path.exists(csv_file):
            with open(csv_file, mode="r", encoding="utf-8") as f:
                row_count = max(0, sum(1 for _ in f) - 1)
                
        send_whatsapp_message(
            sender_number,
            f"📁 *Dataset Export Summary*\n"
            f"- Name: `{data_name}`\n"
            f"- Total Rows: {row_count}\n"
            f"- Local File: `{csv_file}`"
        )
        return

    # 6. Handle !history Command
    if text.lower() == "!history":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT direction, content, timestamp FROM chat_history WHERE sender_number = ? ORDER BY id DESC LIMIT 5",
                (sender_number,)
            )
            rows = cursor.fetchall()
            
        if not rows:
            send_whatsapp_message(sender_number, "No recorded chat history yet.")
            return
            
        history_msg = "🕒 *Recent Chat Memory:*\n"
        for r in reversed(rows):
            prefix = "👤 You" if r["direction"] == "incoming" else "🤖 Bot"
            history_msg += f"- {prefix}: {r['content'][:50]}\n"
        send_whatsapp_message(sender_number, history_msg)
        return

    # Default fallback for regular messages
    send_whatsapp_message(
        sender_number,
        f"🤖 Received your message.\nSend `!guide` to see available data commands or `!TakeInfo` to store data."
    )

# ---------------------------------------------------------------------------
# Flask HTTP Server Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "service": "WhatsApp Data Vault Bot",
        "version": "1.0.0",
        "instance": INSTANCE_NAME,
        "database": DB_PATH
    }), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receives WhatsApp Webhook events from Evolution API."""
    payload = request.get_json(silent=True) or {}
    event = payload.get("event")
    data = payload.get("data", {})
    key = data.get("key", {})
    
    # Process only incoming messages from users; ignore messages from the bot itself
    if event == "MESSAGES_UPSERT" or event == "messages.upsert":
        from_me = key.get("fromMe", False)
        remote_jid = key.get("remoteJid", "")
        message_id = key.get("id", "")
        
        # Ignore status updates or broadcast messages
        if "status@broadcast" in remote_jid or not remote_jid:
            return jsonify({"status": "ignored"}), 200

        # Extract message text across different message schemas
        message_obj = data.get("message", {})
        user_message = (
            message_obj.get("conversation") or
            message_obj.get("extendedTextMessage", {}).get("text") or
            ""
        ).strip()
        
        sender_number = remote_jid.split("@")[0]
        
        # Save incoming message in chat memory
        if user_message:
            with get_db() as conn:
                conn.cursor().execute(
                    "INSERT INTO chat_history (timestamp, remote_jid, sender_number, direction, message_id, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (datetime.utcnow().isoformat(), remote_jid, sender_number, "incoming" if not from_me else "outgoing", message_id, user_message)
                )
                conn.commit()

        # Handle the message if it's sent by a user (not fromMe)
        if not from_me and user_message:
            handle_user_message(sender_number, user_message)

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    print(f"🚀 Starting WhatsApp Data Vault Bot on port {PORT}...")
    print(f"📡 Evolution API: {EVOLUTION_API_URL} (Instance: {INSTANCE_NAME})")
    print(f"📁 Local Storage: {DATA_DIR}")
    app.run(host="0.0.0.0", port=PORT)