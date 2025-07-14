import os
import time
import uuid
import json
from dotenv import load_dotenv
import jwt              # PyJWT
import websocket        # websocket-client

load_dotenv()
API_KEY = os.getenv("COINBASE_API_KEY")
API_SECRET = os.getenv("COINBASE_API_SECRET")
WS_USER_URL = "wss://advanced-trade-ws-user.coinbase.com"

def generate_jwt() -> str:
    now = int(time.time())
    payload = {
        "iss": "cdp",
        "sub": API_KEY,
        "nbf": now,
        "exp": now + 120,
    }
    headers = {
        "kid": API_KEY,
        "nonce": uuid.uuid4().hex,
    }
    return jwt.encode(payload, API_SECRET, algorithm="ES256", headers=headers)

def on_open(ws):
    token = generate_jwt()
    ws.send(json.dumps({
        "type": "subscribe",
        "channel": "user",
        "product_ids": ["BTC-USD"],
        "jwt": token
    }))
    print("🔒 Subscribed to user channel")

def on_message(ws, msg):
    data = json.loads(msg)
    print("📬 Update:", json.dumps(data, indent=2))

def on_error(ws, err):
    print("❌ Error:", err)

def on_close(ws, code, reason):
    print(f"❎ Closed ({code}): {reason}")

def main():
    ws = websocket.WebSocketApp(
        WS_USER_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever(ping_interval=30, ping_timeout=10)

if __name__ == "__main__":
    main()
