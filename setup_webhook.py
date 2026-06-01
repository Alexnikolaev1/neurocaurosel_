#!/usr/bin/env python3
"""
setup_webhook.py — Регистрирует webhook в Telegram.

Запуск ПОСЛЕ деплоя на Vercel:
  python setup_webhook.py

Переменные можно передать через .env или напрямую:
  TELEGRAM_TOKEN=xxx VERCEL_URL=https://your-project.vercel.app python setup_webhook.py
"""

import os
import sys
import urllib.request
import json

# Попробуем загрузить .env если он есть
try:
    from pathlib import Path
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())
except Exception:
    pass

TOKEN = os.environ.get("TELEGRAM_TOKEN")
VERCEL_URL = os.environ.get("VERCEL_URL")

if not TOKEN or not VERCEL_URL:
    print("❌ Укажи TELEGRAM_TOKEN и VERCEL_URL")
    print("   Пример: TELEGRAM_TOKEN=xxx VERCEL_URL=https://proj.vercel.app python setup_webhook.py")
    sys.exit(1)

WEBHOOK_URL = f"{VERCEL_URL.rstrip('/')}/api/bot"
API_URL = f"https://api.telegram.org/bot{TOKEN}/setWebhook"

payload = json.dumps({
    "url": WEBHOOK_URL,
    "max_connections": 40,
    "allowed_updates": ["message", "edited_message", "callback_query"],
    "drop_pending_updates": True,
}).encode()

req = urllib.request.Request(
    API_URL,
    data=payload,
    headers={"Content-Type": "application/json"},
)

with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())

if result.get("ok"):
    print(f"✅ Webhook успешно зарегистрирован: {WEBHOOK_URL}")
else:
    print(f"❌ Ошибка: {result}")
    sys.exit(1)
