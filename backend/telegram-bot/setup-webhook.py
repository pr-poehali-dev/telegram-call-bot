"""
Скрипт для настройки webhook Telegram бота

Использование:
1. Добавьте секрет TELEGRAM_BOT_TOKEN в настройках проекта
2. Запустите этот скрипт локально: python setup-webhook.py
"""

import os
import requests

TELEGRAM_BOT_TOKEN = "8107172432:AAEfZlmEo2i2_9w0JClHO0mgTv11oGAhQuk"
WEBHOOK_URL = "https://functions.poehali.dev/387a2d96-07f1-426a-bdb1-1f24a1dda4e1"

def setup_webhook():
    """Настройка webhook для Telegram бота"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    
    payload = {
        "url": WEBHOOK_URL,
        "allowed_updates": ["message", "callback_query"]
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("ok"):
            print("✅ Webhook успешно установлен!")
            print(f"URL: {WEBHOOK_URL}")
        else:
            print(f"❌ Ошибка: {result.get('description')}")
    else:
        print(f"❌ HTTP ошибка: {response.status_code}")
        print(response.text)

def check_webhook():
    """Проверка текущих настроек webhook"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    
    response = requests.get(url)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("ok"):
            info = result.get("result", {})
            print("\n📋 Текущие настройки webhook:")
            print(f"URL: {info.get('url', 'не установлен')}")
            print(f"Pending updates: {info.get('pending_update_count', 0)}")
            if info.get('last_error_date'):
                print(f"⚠️ Последняя ошибка: {info.get('last_error_message')}")
        else:
            print(f"❌ Ошибка: {result.get('description')}")
    else:
        print(f"❌ HTTP ошибка: {response.status_code}")

if __name__ == "__main__":
    print("🚀 Настройка Telegram бота...\n")
    setup_webhook()
    check_webhook()
    print("\n✅ Готово! Бот запущен и готов к работе.")
    print("\nОтправьте /start вашему боту в Telegram чтобы начать!")
