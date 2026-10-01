# Evolution API, Coolify & WhatsApp Bot Infrastructure Report

**Generated At:** 2026-10-01  
**Environment:** Arch / Omarchy Linux (`Linux 7.2.3-arch1-3 x86_64`) • Docker Engine 29.7.2 • Coolify 4.3.23  
**Target Path:** `/home/john-smith/agy-workspace/Coding/Practice/Python/whatsappp/report.md`

---

## 1. System & Service Architecture Overview

The system consists of three interconnected layers:
1. **Coolify Ingress & Orchestration**: Coolify PaaS running on `http://localhost:8000` managing Docker containers and Traefik v3 reverse proxy (`coolify-proxy`).
2. **Evolution API Stack (WhatsApp Bridge)**:
   - **Core Engine**: `evoapicloud/evolution-api:v2.3.7` running on internal port `8080`.
   - **Database**: PostgreSQL 16 (`postgres-hcoka1lffshxmnxquji5smug`).
   - **Cache & Queue**: Redis 7 (`redis-hcoka1lffshxmnxquji5smug`).
   - **Ingress**: Traefik routing domains via host ports `80` and `443`.
3. **Custom WhatsApp Bot (`whatsappp` / `wabot`)**:
   - FastAPI application configured to run on port `9000`.
   - Receives WhatsApp message webhooks from Evolution API and triggers replies.

---

## 2. Essential Credentials, URLs & Tokens

### Evolution API
* **Manager Web UI**: `http://evo-hcoka1lffshxmnxquji5smug.localhost.sslip.io/manager/`
* **API Base URL**: `http://evo-hcoka1lffshxmnxquji5smug.localhost.sslip.io`
* **Global API Key** (`AUTHENTICATION_API_KEY`): `xvOagvh8NKcj8mOZ7VQq0lCuaAyt92iu`
* **Active Instance Name**: `whatsapp-1`
* **Instance ID**: `45c0a2c0-033f-4fe4-89db-8f27a0b3eacc`
* **Instance Token**: `9BFA2242-03E7-4EB5-8800-FFE37D300A7C`
* **Internal Database URL**: `postgresql://xDbdq76fLZ1AXlYT:maf94WaWq8r3u6qkW1nvqmU2OtLmjR7V@postgres:5432/postgres`

### Coolify Platform
* **Coolify Dashboard**: `http://localhost:8000`
* **Bot Project Name**: `Organiser ` (UUID: `jtl84hfrbw0mutyhekm5wxnr`)
* **Environment**: `production` (UUID: `5g2vrropoytjuizmvioxa2us`)
* **Bot Application UUID**: `ayrj8cbeelb5bmijnosucyia`
* **Bot Domain**: `http://whatsappp.ayrj8cbeelb5bmijnosucyia.localhost.sslip.io`
* **Bot Internal Port**: `9000`

---

## 3. Core Technical Issues Diagnosed & Resolved

### Issue A: "No Available Server" (HTTP 503) When Opening Domain
* **Symptom**: Browser displayed `503 Service Unavailable: no available server` and untrusted certificate warnings (`CN=TRAEFIK DEFAULT CERT`).
* **Root Cause**: Modern web browsers automatically force **HTTPS (port 443)**. In Coolify, Evolution API was configured only with `http://...`, creating a Traefik router on port 80 only. Unmatched port 443 requests hit Traefik's fallback `catchall` router which pointed to a dummy `noop` service (`servers: {}`), returning 503.
* **Resolution**: Access explicitly using `http://` in private browsing mode, or configure HTTPS certificates in Coolify.

---

### Issue B: WhatsApp Pairing QR Code Blank in Modal
* **Symptom**: Clicking "Scan QR Code" opened a popup saying *"Scan the QR code with your WhatsApp Web"*, but the QR code image area remained completely blank.
* **Root Cause**:
  1. Evolution API's Baileys engine does not generate QR codes locally; it must establish a live TLS WebSocket connection to `wss://web.whatsapp.com:443`.
  2. The host's native **nftables** firewall had a default forward drop:
     ```text
     table inet filter {
         chain forward {
             type filter hook forward priority filter; policy drop;
         }
     }
     ```
  3. Every packet sent from the Docker container to the Internet was dropped by the kernel (100% packet loss to `163.70.140.60:443` and `8.8.8.8`). Baileys was trapped in an infinite retry loop, returning `{"count": 0}`.
* **Resolution Rule**: Add forward acceptance rules to nftables:
  ```bash
  sudo nft add rule inet filter forward ct state established,related accept
  sudo nft add rule inet filter forward iifname "br-*" accept
  sudo nft add rule inet filter forward oifname "br-*" accept
  ```

---

### Issue C: "Error: P1001 Can't reach database server at postgres:5432" After Reboot
* **Symptom**: After a system reboot, all domain links failed with 502/503. Evolution API container was in a continuous restart loop (`Restarting (1)`).
* **Root Cause**:
  1. On system reboot, the Linux kernel reset `net.bridge.bridge-nf-call-iptables` back to `1`.
  2. With this sysctl enabled, Docker 29 raw table rules (`-A PREROUTING ! -i br-... -j DROP`) dropped inter-container bridge traffic.
  3. `api` could not reach `postgres:5432`, crashing Prisma database migrations.
* **Resolution & Permanent Fix**:
  1. Applied runtime fix: `sysctl -w net.bridge.bridge-nf-call-iptables=0`.
  2. Persisted permanently in `/etc/sysctl.d/99-docker-bridge.conf`:
     ```ini
     net.bridge.bridge-nf-call-iptables = 0
     net.bridge.bridge-nf-call-ip6tables = 0
     net.bridge.bridge-nf-call-arptables = 0
     ```

---

### Issue D: Coolify Host SSH Connection Failure (`Connection refused`)
* **Symptom**: Coolify failed deployments with: `ssh: connect to host 127.0.0.1 port 22: Connection refused`.
* **Root Cause**: The localhost server entry in Coolify had its IP set to `127.0.0.1`. Inside the Coolify Docker container, `127.0.0.1` refers to the container itself (which does not run SSH), not the host machine.
* **Resolution**: Restored the server IP to `host.docker.internal` (reaching host SSH on `10.0.0.1:22`).

---

### Issue E: Bot Deployment Failed (`fatal: Remote branch main not found`)
* **Symptom**: Building `jamessmithtitit-jpg/Whatsappp` failed during `git clone`.
* **Root Cause**: The repository `https://github.com/jamessmithtitit-jpg/Whatsappp` was created on GitHub but has **0 commits / 0 files** (`Git Repository is empty`).
* **Resolution**: You need to write and push `main.py` (or `bot.py`) and a `Dockerfile` to that repository, or use the reference repo `https://github.com/rajumanoj333/wabot` (branch: `master`).

---

## 4. WhatsApp Bot Architecture & Implementation Guide

### Webhook Flow
```text
WhatsApp User ──> WhatsApp Servers ──> Evolution API (Port 8080)
                                              │
                                              ▼ (HTTP POST /webhook)
                                         FastAPI Bot (Port 9000)
                                              │
WhatsApp User <── WhatsApp Servers <── Evolution API (/message/sendText)
```

### Complete Bot Implementation (`bot.py` / `main.py`)
```python
import os
import requests
from fastapi import FastAPI, Request

app = FastAPI(title="WhatsApp Organizer Bot")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://evo-hcoka1lffshxmnxquji5smug.localhost.sslip.io")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "xvOagvh8NKcj8mOZ7VQq0lCuaAyt92iu")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "whatsapp-1")

@app.get("/")
def health_check():
    return {"status": "ok", "bot": "running"}

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    
    event = payload.get("event")
    data = payload.get("data", {})
    key = data.get("key", {})
    
    # Process incoming messages; avoid infinite reply loops by ignoring fromMe messages
    if event == "messages.upsert" and not key.get("fromMe"):
        remote_jid = key.get("remoteJid", "")
        message_obj = data.get("message", {})
        user_message = (
            message_obj.get("conversation") or 
            message_obj.get("extendedTextMessage", {}).get("text") or 
            ""
        ).strip()
        
        if user_message:
            sender_number = remote_jid.split("@")[0]
            
            # Bot decision logic
            if user_message.lower() == "/help":
                reply = "Commands:\n- /help: Show help\n- /ping: Ping check"
            elif user_message.lower() == "/ping":
                reply = "Pong! 🏓"
            else:
                reply = f"Organiser received: {user_message}"
                
            # Send message back via Evolution API
            send_url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
            headers = {
                "apikey": EVOLUTION_API_KEY,
                "Content-Type": "application/json"
            }
            body = {
                "number": sender_number,
                "text": reply
            }
            
            try:
                requests.post(send_url, json=body, headers=headers, timeout=10)
            except Exception as e:
                print(f"[Error] Failed to send message: {e}")
                
    return {"status": "success"}
```

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn requests
COPY . .
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
```

---

## 5. Webhook Registration in Evolution API

Once the bot is deployed on port 9000:
1. Open Evolution API Manager (`http://evo-hcoka1lffshxmnxquji5smug.localhost.sslip.io/manager/`).
2. Select instance `whatsapp-1` ➔ Click **Webhook**.
3. Set **URL**: `http://whatsappp.ayrj8cbeelb5bmijnosucyia.localhost.sslip.io/webhook`
4. Toggle **Enabled**: `ON`.
5. Select Event: `MESSAGES_UPSERT`.
6. Click **Save**.
