# 📖 WhatsApp Data Vault & Memory Bot Guide

This bot connects to **Evolution API**, records complete chat history into a local SQLite database, and acts as a **secure personal data vault** that saves your structured or multi-message notes into well-formed **CSV files** on your computer.

---

## 🚀 Quick Start & Running the Bot

Run the bot locally inside the virtual environment:
```bash
source .venv/bin/activate
python main.py
```
By default, the server starts on `http://0.0.0.0:9000`.

---

## 📁 Where Data is Stored
* **Local Database:** `./data/memory.db`  
  * `chat_history`: Every incoming and outgoing message with timestamp and sender.
  * `datasets`: Registry of dataset names, salted password hashes, and owner numbers.
  * `active_sessions`: Tracks ongoing multi-message collection sessions.
  * `data_records`: Individual structured records.
* **Local CSV Files:** `./data/<data_name>.csv`  
  * Every dataset gets its own cleanly formatted CSV file with columns:
    `record_id`, `timestamp_utc`, `data_name`, `sender_number`, `format_detected`, `content`

---

## 🔒 Security Model
* **Salted SHA-256 Hashing:** When you create a dataset using `!TakeInfo <data_name> <data_pass>`, the password is salt-hashed.
* **Access Control:** Any future attempt to append data to `<data_name>`, view records, or export stats **must** provide the matching `<data_pass>`. If the password is wrong, access is denied.

---

## 💬 WhatsApp Commands & Triggers

### 1. Ingest Data in a Single Message
Save data immediately on the same line:
```text
!TakeInfo <data_name> <data_pass> <your data content>
```
**Examples:**
* Key-Value data:
  ```text
  !TakeInfo grocery mypass Apples: 1kg, Milk: 2L, Bread: 1 loaf
  ```
* JSON data:
  ```text
  !TakeInfo clients pass123 {"name": "Alice", "phone": "9876543210", "city": "Delhi"}
  ```
* Tabular / CSV row:
  ```text
  !TakeInfo sales pass123 2026-10-01, ProductA, 450, Success
  ```

---

### 2. Multi-Message Data Ingestion
If you have multiple items or paragraphs that you want to send across several messages:

1. **Start the session:**
   ```text
   !TakeInfo <data_name> <data_pass>
   ```
2. **Send your messages one by one:**
   ```text
   Item 1: Complete project documentation
   ```
   ```text
   Item 2: Fix Traefik reverse proxy configuration
   ```
   ```text
   Item 3: Backup PostgreSQL database
   ```
3. **Save and finish:**
   ```text
   !done
   ```
   *(or type `!save`)*
4. **To cancel without finishing:**
   ```text
   !cancel
   ```

---

### 3. View Recent Records
View the latest 5 entries from a dataset:
```text
!ViewInfo <data_name> <data_pass>
```

---

### 4. Export & File Summary
Check total rows stored and the file path on the machine:
```text
!Export <data_name> <data_pass>
```

---

### 5. Chat Memory History
View recent conversation messages preserved in memory:
```text
!history
```

---

### 6. Interactive Guide
Get instructions sent directly to your WhatsApp chat:
```text
!guide
```
*(or `!help`)*
