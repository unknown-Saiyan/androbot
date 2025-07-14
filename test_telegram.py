import requests

TELEGRAM_BOT_TOKEN = "7643009409:AAHwz0Xo16jez1tMQUhqbn6WZzBciLvBZlE"
TELEGRAM_CHAT_ID = "7296843245"
TEXT = "✅ ¡Mensaje de prueba exitoso desde tu bot, Andrés!"

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": TEXT
}

response = requests.post(url, json=payload)
print("Status:", response.status_code)
print("Response:", response.text)
