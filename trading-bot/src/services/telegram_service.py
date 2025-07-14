import os
import requests
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str) -> bool:
    """Send a message to a Telegram chat."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")
        return False

def send_telegram_alert(alert_type: str, details: str) -> None:
    """Send an alert message to Telegram."""
    message = f"⚠️ <b>{alert_type}</b>\n{details}"
    send_telegram_message(message)