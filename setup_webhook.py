#!/usr/bin/env python3
"""
setup_webhook.py — Регистрирует webhook в Telegram (локально, один раз).

PowerShell:
  $env:TELEGRAM_TOKEN = "123:ABC..."
  $env:VERCEL_URL = "https://your-project.vercel.app"
  python setup_webhook.py

Или положи TELEGRAM_TOKEN и VERCEL_URL в файл .env в корне проекта.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Установи зависимости: pip install httpx")
    sys.exit(1)

TELEGRAM_HOST = "api.telegram.org"


def load_dotenv() -> None:
    env_file = Path(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


def clean(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip('"').strip("'")


def check_dns(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443)
        return True
    except socket.gaierror:
        return False


def main() -> int:
    load_dotenv()

    token = clean(os.environ.get("TELEGRAM_TOKEN"))
    vercel_url = clean(os.environ.get("VERCEL_URL"))

    if not token or not vercel_url:
        print("❌ Нужны TELEGRAM_TOKEN и VERCEL_URL")
        print()
        print("PowerShell:")
        print('  $env:TELEGRAM_TOKEN = "токен_от_BotFather"')
        print('  $env:VERCEL_URL = "https://твой-проект.vercel.app"')
        print("  python setup_webhook.py")
        print()
        print("Или создай .env с этими двумя строками.")
        return 1

    if not re.match(r"^\d+:[A-Za-z0-9_-]+$", token):
        print("❌ TELEGRAM_TOKEN выглядит неверно (ожидается формат 123456789:ABCdef...)")
        print("   Проверь .env — без пробелов, кавычек и лишних символов в конце строки.")
        return 1

    if not vercel_url.startswith("https://"):
        print("❌ VERCEL_URL должен начинаться с https://")
        print(f"   Сейчас: {vercel_url}")
        return 1

    webhook_url = f"{vercel_url.rstrip('/')}/api/bot"

    print(f"Проверяю DNS для {TELEGRAM_HOST}...")
    if not check_dns(TELEGRAM_HOST):
        print()
        print("❌ Не удаётся найти api.telegram.org (getaddrinfo failed).")
        print("   Это проблема сети/DNS на твоём ПК, не Vercel.")
        print()
        print("Что попробовать:")
        print("  1. Открой в браузере: https://api.telegram.org")
        print("  2. Смени DNS на 8.8.8.8 или 1.1.1.1")
        print("  3. Отключи VPN / прокси или наоборот включи VPN")
        print("  4. Зарегистрируй webhook через браузер (см. README)")
        print()
        print("Альтернатива в PowerShell (если сайт открывается):")
        print('  $t = "ТВОЙ_ТОКЕН"')
        print(f'  $body = \'{{"url":"{webhook_url}","drop_pending_updates":true}}\'')
        print('  Invoke-RestMethod -Uri "https://api.telegram.org/bot$t/setWebhook" `')
        print('    -Method Post -ContentType "application/json" -Body $body')
        return 1

    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "max_connections": 40,
        "allowed_updates": ["message", "edited_message", "callback_query"],
        "drop_pending_updates": True,
    }

    print(f"Регистрирую webhook → {webhook_url}")

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(api_url, json=payload)
            result = r.json()
    except httpx.ConnectError as exc:
        print(f"❌ Нет соединения с Telegram API: {exc}")
        return 1

    if result.get("ok"):
        print(f"✅ Webhook зарегистрирован: {webhook_url}")
        info = httpx.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=30.0)
        info_data = info.json().get("result", {})
        print(f"   URL: {info_data.get('url', '—')}")
        if info_data.get("last_error_message"):
            print(f"   ⚠️ last_error: {info_data['last_error_message']}")
        print()
        print("Проверь деплой в браузере (должно быть «NeuroCarousel bot is alive!»):")
        print(f"   {webhook_url}")
        return 0

    print(f"❌ Telegram ответил: {result}")
    desc = result.get("description", "")
    if "HTTPS" in desc or "certificate" in desc.lower():
        print("   Проверь, что Vercel задеплоен и URL открывается в браузере.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
