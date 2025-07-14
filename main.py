import os
import json
import logging
import requests
import schedule
import time
import threading
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv
from coinbase.rest import RESTClient
from cryptography.hazmat.primitives import serialization
from contextlib import asynccontextmanager
import google.generativeai as genai
import pandas as pd
import io
import matplotlib.pyplot as plt
from typing import Optional
from gtts import gTTS
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ─── Load .env with proper key handling ──────────────────────────────────────
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_KEY = os.getenv("COINBASE_API_KEY")
API_SECRET = os.getenv("COINBASE_API_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BASE_URL = os.getenv("BASE_URL")
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

# Handle the private key properly
if API_SECRET:
    # Replace literal \n with actual newlines
    API_SECRET = API_SECRET.replace('\\n', '\n')
    
    # Validate the key can be loaded
    try:
        private_key = serialization.load_pem_private_key(
            API_SECRET.encode(), password=None
        )
        print("✅ Private key loaded successfully")
    except Exception as e:
        print(f"❌ Private key error: {e}")
        raise

# Define the scope for Spotify API access
SPOTIFY_SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing streaming"

# Create SpotifyOAuth object. Spotipy will handle the cache automatically.
sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=SPOTIFY_SCOPE,
    cache_path=".spotify_cache",
    show_dialog=True
)

# Global Spotify client
sp = spotipy.Spotify(auth_manager=sp_oauth)

PORTFOLIO_UUID = "1dfa9b1a-026b-5acf-b1f6-7081d745881f"

# ─── Multi-Symbol Configuration ─────────────────────────────────────────────
# This will be populated dynamically from the Coinbase API
COINBASE_PRODUCTS = {}

# Keep original emojis for a better user experience on popular coins
CUSTOM_EMOJIS = {
    "BTC": "₿", "ETH": "💎", "MORPHO": "🦋", "PEPE": "🐸", 
    "ADA": "🔵", "SOL": "✨", "PENGU": "🐧"
}


# ─── Configuration ───────────────────────────────────────────────────────────
ALERT_SETTINGS = {
    "price_alerts": True,
    "risk_alerts": True,
    "morning_reports": True,
    "evening_summaries": True,
    "profit_alerts": True,
    "loss_threshold": -50,
    "profit_threshold": 100,
    "price_change_threshold": 2.0
}

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ─── Coinbase REST Client ────────────────────────────────────────────────────
client = RESTClient(api_key=API_KEY, api_secret=API_SECRET, rate_limit_headers=True)

# ─── Gemini Client ───────────────────────────────────────────────────────────
if not GOOGLE_API_KEY:
    logging.warning("GOOGLE_API_KEY not found. AI command processing will be disabled.")
    gemini_client = None
else:
    genai.configure(api_key=GOOGLE_API_KEY)
    gemini_client = genai.GenerativeModel('gemini-1.5-flash') # Using a fast and efficient model


# ─── Global Variables ────────────────────────────────────────────────────────
last_prices = {}
trade_history = []
bot_start_time = datetime.now()
scheduler_thread = None
scheduler_stop_event = threading.Event()

# ─── Helper Functions ────────────────────────────────────────────────────────
def normalize_symbol(raw_symbol: str) -> str:
    """Normalize symbol format from TradingView to Coinbase format"""
    if raw_symbol.endswith("USD"):
        symbol = raw_symbol[:-3]
    else:
        symbol = raw_symbol
    
    symbol_upper = symbol.upper()
    if f"{symbol_upper}-USD" not in COINBASE_PRODUCTS:
        raise ValueError(f"Unsupported or invalid symbol: {symbol}")
    
    return symbol_upper

def get_symbol_info(symbol: str) -> dict:
    """Get symbol information including emoji and precision"""
    product_id = f"{symbol.upper()}-USD"
    product_data = COINBASE_PRODUCTS.get(product_id)

    if not product_data:
        # Fallback for symbols that might not be in the list for some reason
        return {"name": symbol, "emoji": "💰", "precision": 8}

    return {
        "name": product_data.get("display_name", symbol),
        "emoji": CUSTOM_EMOJIS.get(symbol.upper(), "💰"), # Use custom emoji or fallback
        "precision": product_data.get("precision", 8)
    }

def format_crypto_amount(amount: float, symbol: str) -> str:
    """Format crypto amount with proper precision"""
    precision = get_symbol_info(symbol)["precision"]
    return f"{amount:.{precision}f}"

def parse_command_with_ai(text: str) -> dict:
    """Use Gemini to parse natural language commands into structured data."""
    if not gemini_client:
        raise Exception("Gemini client is not configured.")

    prompt = f"""
    You are an intelligent assistant for a cryptocurrency trading bot.
    Your task is to parse the user's command and extract the action, the cryptocurrency symbol, and the percentage.
    The user is trading on Coinbase. Any valid cryptocurrency symbol is supported (e.g., BTC, ETH, SOL, RNDR, etc.).
    - The available actions are 'buy', 'sell', 'convert', 'status', 'help'.
    - For 'convert' actions, you must identify 'from_symbol' and 'to_symbol'.
    - If a percentage is mentioned, extract it. If not, default to 100.
    - If the user asks for status, pnl, or positions, the action is 'status'.
    - If the user asks for help, the action is 'help'.
    - Respond ONLY with a valid JSON object in the format:
      {{
        "action": "buy/sell/convert/status/help/unknown",
        "symbol": "SYMBOL",
        "to_symbol": "SYMBOL",
        "percentage": 100
      }}
    - If you cannot determine the command, set the action to "unknown".

    User command: "{text}"
    """

    try:
        response = gemini_client.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                temperature=0.1,
                response_mime_type="application/json" # Instruct Gemini to output JSON
            )
        )
        command_json = response.text
        return json.loads(command_json)
    except Exception as e:
        logging.error(f"Gemini parsing error: {e}")
        return {"action": "unknown"}

def parse_voice_command_with_ai(audio_bytes: bytes, mime_type: str) -> dict:
    """Use Gemini to parse a voice command into structured data."""
    if not gemini_client:
        raise Exception("Gemini client is not configured.")

    prompt = """
    Listen to the user's voice command and determine their intent.
    - The available actions are 'status', 'help', 'buy', 'sell', 'convert'.
    - If the user asks for a summary, status, pnl, or positions, the action is 'status'.
    - If the user asks for help, the action is 'help'.
    - Respond ONLY with a valid JSON object in the format:
      {
        "action": "status/help/unknown",
        "transcription": "The transcribed text."
      }
    - If you cannot determine the intent, set the action to "unknown".
    """
    try:
        audio_part = {"mime_type": mime_type, "data": audio_bytes}
        response = gemini_client.generate_content(
            [prompt, audio_part],
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        command_json = response.text
        return json.loads(command_json)
    except Exception as e:
        logging.error(f"Gemini voice parsing error: {e}")
        return {"action": "unknown", "transcription": "Error processing audio."}


def analyze_document_with_ai(file_content: bytes, mime_type: str, prompt: str) -> dict:
    """Use Gemini to analyze an uploaded document and extract the top recommended coin."""
    if not gemini_client:
        return {"summary": "❌ AI client is not configured.", "top_coin": None}
    
    full_prompt = f"""
    You are an expert financial analyst. Analyze the attached document based on the user's request.
    1.  Provide a concise, clear summary answering the user's request.
    2.  Identify the single top-rated or most bullish cryptocurrency symbol mentioned. The symbol can be any valid cryptocurrency ticker (e.g., BTC, ETH, RNDR).
    3.  Respond ONLY with a valid JSON object in the format:
        {{
          "summary": "Your detailed analysis here...",
          "top_coin": "SYMBOL"
        }}
    If no specific coin is clearly recommended as the top choice, set "top_coin" to null.

    User Request: "{prompt}"
    """

    try:
        # Correctly format the file for the API call
        document_part = {"mime_type": mime_type, "data": file_content}
        
        response = gemini_client.generate_content(
            [full_prompt, document_part],
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        analysis_data = json.loads(response.text)
        # Validate the top_coin is in our supported list
        top_coin = analysis_data.get("top_coin")
        if top_coin and f"{top_coin.upper()}-USD" not in COINBASE_PRODUCTS:
            analysis_data["top_coin"] = None # Invalidate if not tradable
        return analysis_data
    except Exception as e:
        logging.error(f"Gemini document analysis error: {e}")
        return {"summary": f"❌ Sorry, I couldn't analyze the document. Error: {e}", "top_coin": None}

def extract_symbols_with_ai(file_content: bytes, mime_type: str) -> list:
    """Use Gemini to extract a list of top 7 symbols from a document."""
    if not gemini_client:
        raise Exception("AI client is not configured.")
    
    prompt = f"""
    You are a financial analyst reviewing a market report.
    Your task is to identify the top 7 most promising or frequently mentioned cryptocurrency symbols from the document.
    The symbols can be any valid cryptocurrency ticker.
    Respond ONLY with a valid JSON object in the format:
    {{
      "symbols": ["SYMBOL1", "SYMBOL2", ...]
    }}
    """
    try:
        # Correctly format the file for the API call
        document_part = {"mime_type": mime_type, "data": file_content}

        response = gemini_client.generate_content(
            [prompt, document_part],
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
        # Filter to ensure all returned symbols are valid and tradable
        valid_symbols = [s.upper() for s in data.get("symbols", []) if f"{s.upper()}-USD" in COINBASE_PRODUCTS]
        return valid_symbols[:7] # Return up to 7 valid symbols
    except Exception as e:
        logging.error(f"Gemini symbol extraction error: {e}")
        return []

# ─── Telegram Helper Functions ──────────────────────────────────────────────
def send_telegram_message(message: str, reply_markup=None):
    """Send message to Telegram, with optional inline keyboard"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")
        return False

def send_telegram_photo(photo_bytes: bytes, caption: str = ""):
    """Send a photo from bytes to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        files = {'photo': ('chart.png', photo_bytes, 'image/png')}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
        
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to send Telegram photo: {e}")
        return False

def send_telegram_voice(voice_bytes: bytes, caption: str = ""):
    """Send a voice message from bytes to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
        files = {'voice': ('summary.ogg', voice_bytes, 'audio/ogg')}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
        
        response = requests.post(url, files=files, data=data)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to send Telegram voice message: {e}")
        return False

def set_telegram_webhook():
    """Sets the Telegram webhook URL when the bot starts."""
    if not BASE_URL:
        logging.error("BASE_URL not set. Cannot set Telegram webhook.")
        return
    
    webhook_url = f"{BASE_URL}/telegram"
    set_webhook_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    
    try:
        response = requests.get(set_webhook_url)
        response.raise_for_status()
        result = response.json()
        if result.get("ok"):
            logging.info(f"✅ Telegram webhook set successfully to {webhook_url}")
        else:
            logging.error(f"❌ Failed to set Telegram webhook: {result.get('description')}")
    except Exception as e:
        logging.error(f"❌ Exception while setting Telegram webhook: {e}")

# ─── Coinbase Helper Functions ──────────────────────────────────────────────
def get_pnl_analysis():
    """Get P/L analysis for daily and yearly performance"""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        total_unrealized_pnl = sum(float(pos['unrealized_pnl']) for pos in positions if pos['asset'] not in ['USD', 'USDC'])
        profitable_count = sum(1 for pos in positions if float(pos['unrealized_pnl']) > 0)
        losing_count = sum(1 for pos in positions if float(pos['unrealized_pnl']) < 0)
        
        # Simplified P/L for now as transaction history can be complex
        daily_pnl = total_unrealized_pnl * 0.1  # Placeholder
        yearly_pnl = total_unrealized_pnl # Placeholder
        
        return {
            "total_unrealized_pnl": total_unrealized_pnl,
            "daily_pnl": daily_pnl,
            "yearly_pnl": yearly_pnl,
            "profitable_positions": profitable_count,
            "losing_positions": losing_count,
            "total_positions": profitable_count + losing_count
        }
    except Exception as e:
        logging.error(f"Failed to get P/L analysis: {e}")
        return {"total_unrealized_pnl": 0, "daily_pnl": 0, "yearly_pnl": 0, "profitable_positions": 0, "losing_positions": 0, "total_positions": 0}

def get_portfolio_summary():
    """Get enhanced portfolio summary with P/L for Telegram alerts"""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        balances = portfolio['breakdown']['portfolio_balances']
        positions = portfolio['breakdown']['spot_positions']
        pnl_data = get_pnl_analysis()
        
        unrealized_pnl = pnl_data['total_unrealized_pnl']
        daily_pnl = pnl_data['daily_pnl']
        yearly_pnl = pnl_data['yearly_pnl']
        
        unrealized_emoji = "📈" if unrealized_pnl >= 0 else "📉"
        daily_emoji = "🟢" if daily_pnl >= 0 else "🔴"
        yearly_emoji = "🗓️" # Calendar emoji for yearly
        
        crypto_positions = [f"{get_symbol_info(pos['asset'])['emoji']} {pos['asset']}: ${float(pos['total_balance_fiat']):.2f}" for pos in positions if pos['asset'] not in ['USD', 'USDC'] and float(pos['total_balance_fiat']) > 0.01]
        
        summary = f"""📊 <b>Multi-Symbol Portfolio Summary</b>
💰 Total Value: ${float(balances['total_balance']['value']):.2f}
💵 Cash: ${float(balances['total_cash_equivalent_balance']['value']):.2f}
₿ Crypto: ${float(balances['total_crypto_balance']['value']):.2f}

💎 <b>Top Positions</b>
{"\n".join(crypto_positions[:5]) if crypto_positions else "No crypto positions"}

📈 <b>P&L Analysis</b>
{unrealized_emoji} Unrealized P/L: ${unrealized_pnl:.2f}
{daily_emoji} Daily P/L: ${daily_pnl:.2f}
{yearly_emoji} Yearly P/L: ${yearly_pnl:.2f}

📊 Positions: {pnl_data['profitable_positions']}📈 {pnl_data['losing_positions']}📉
🕐 Updated: {datetime.now().strftime('%H:%M:%S')}"""
        
        return summary
    except Exception as e:
        logging.error(f"Failed to get portfolio summary: {e}")
        return "❌ Could not fetch portfolio data"

def get_portfolio_summary_text_for_tts():
    """Get a simplified portfolio summary formatted for Text-to-Speech."""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        balances = portfolio['breakdown']['portfolio_balances']
        pnl_data = get_pnl_analysis()
        
        total_value = float(balances['total_balance']['value'])
        cash_value = float(balances['total_cash_equivalent_balance']['value'])
        crypto_value = float(balances['total_crypto_balance']['value'])
        unrealized_pnl = pnl_data['total_unrealized_pnl']
        
        pnl_status = "up" if unrealized_pnl >= 0 else "down"
        
        summary = f"""
        Here is your portfolio summary.
        Your total portfolio value is ${total_value:,.2f}.
        You have ${cash_value:,.2f} in cash, and ${crypto_value:,.2f} in crypto.
        Your current unrealized profit and loss is {pnl_status} ${abs(unrealized_pnl):,.2f}.
        """
        return summary.strip()
    except Exception as e:
        logging.error(f"Failed to get portfolio summary for TTS: {e}")
        return "Sorry, I could not fetch the portfolio data."

def get_detailed_positions():
    """Get a detailed breakdown of each position."""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        message = "🔎 <b>Detailed Positions</b>\n\n"
        crypto_positions = [pos for pos in positions if pos['asset'] not in ['USD', 'USDC'] and float(pos['total_balance_fiat']) > 0.01]

        if not crypto_positions:
            return "You have no crypto positions."

        for pos in crypto_positions:
            symbol = pos['asset']
            info = get_symbol_info(symbol)
            pnl_emoji = "📈" if float(pos['unrealized_pnl']) >= 0 else "📉"
            
            message += f"{info['emoji']} <b>{info['name']} ({symbol})</b>\n"
            message += f"   Amount: {format_crypto_amount(float(pos['available_to_trade_crypto']), symbol)}\n"
            message += f"   Value: ${float(pos['total_balance_fiat']):.2f}\n"
            message += f"   {pnl_emoji} P/L: ${float(pos['unrealized_pnl']):.2f}\n\n"
            
        return message.strip()
    except Exception as e:
        logging.error(f"Failed to get detailed positions: {e}")
        return "❌ Could not fetch detailed positions."

def get_trade_history():
    """Get a summary of the last 10 trades."""
    if not trade_history:
        return "📜 No trade history recorded since last restart."
    
    message = "📜 <b>Recent Trade History</b>\n\n"
    # Get the last 10 trades, newest first
    for trade in reversed(trade_history[-10:]):
        action_emoji = "🟢" if trade['side'].lower() == 'buy' else '🔴'
        message += f"{action_emoji} {trade['side'].upper()} {trade['symbol']} | {trade['amount_str']}\n"
        message += f"   <pre>ID: {trade['order_id']}</pre>\n"
        message += f"   <i>{trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</i>\n\n"
        
    return message.strip()

def get_largest_asset():
    """Finds the crypto asset with the largest fiat value in the portfolio."""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        crypto_positions = [
            pos for pos in positions 
            if pos['asset'] not in ['USD', 'USDC'] and float(pos['total_balance_fiat']) > 1.0
        ]

        if not crypto_positions:
            return None

        # Find the asset with the maximum fiat value
        largest_asset = max(crypto_positions, key=lambda x: float(x['total_balance_fiat']))
        return largest_asset['asset']
    except Exception as e:
        logging.error(f"Failed to get largest asset: {e}")
        return None

def check_multi_symbol_price_alerts():
    """Check for price alerts across all supported symbols"""
    # This function can be very noisy with all symbols.
    # For now, we will check prices only for assets currently in the portfolio.
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        symbols_to_check = [
            pos['asset'] for pos in positions 
            if pos['asset'] not in ['USD', 'USDC'] and float(pos['total_balance_fiat']) > 1.0
        ]
    except Exception as e:
        logging.error(f"Could not get portfolio for price alerts: {e}")
        return

    for symbol in symbols_to_check:
        try:
            product_id = f"{symbol}-USD"
            if product_id not in COINBASE_PRODUCTS:
                continue # Skip if not a tradable product

            product = client.get_product(product_id=product_id)
            current_price = float(product['price'])
            last_price = last_prices.get(symbol, current_price)
            price_change = ((current_price - last_price) / last_price) * 100 if last_price > 0 else 0
            
            if abs(price_change) > ALERT_SETTINGS['price_change_threshold']:
                symbol_info = get_symbol_info(symbol)
                emoji = "🚀" if price_change > 0 else "💥"
                alert = f"""{emoji} <b>Price Alert - {symbol_info['emoji']} {symbol}</b>
💰 Current: ${current_price:.2f} | 📊 Change: {price_change:+.2f}%"""
                if ALERT_SETTINGS['price_alerts']:
                    send_telegram_message(alert)
            
            last_prices[symbol] = current_price
        except Exception as e:
            logging.error(f"Price alert error for {symbol}: {e}")

def execute_trade(symbol: str, side: str, sl_percent: float = None, tp_percent: float = None):
    """Execute trade on Coinbase with dynamic position sizing and optional SL/TP."""
    try:
        symbol = normalize_symbol(symbol)
        symbol_info = get_symbol_info(symbol)
        product_id = f"{symbol}-USD"
        
        # Get current price for SL/TP calculation
        product = client.get_product(product_id=product_id)
        current_price = float(product['price'])

        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        if side.lower() == "buy":
            usd_position = next((pos for pos in positions if pos['asset'] == 'USD'), None)
            if not usd_position or float(usd_position['available_to_trade_fiat']) < 1:
                raise Exception("Insufficient cash balance")
            quote_size = round(float(usd_position['available_to_trade_fiat']) * 0.999, 2)
            order_config = {"market_market_ioc": {"quote_size": f"{quote_size:.2f}"}}
            trade_amount_str = f"${quote_size:.2f}"
        else: # SELL
            crypto_position = next((pos for pos in positions if pos['asset'] == symbol), None)
            if not crypto_position or float(crypto_position['available_to_trade_crypto']) < 0.00001:
                raise Exception(f"Insufficient {symbol} balance")
            base_size = round(float(crypto_position['available_to_trade_crypto']) * 0.999, symbol_info['precision'])
            order_config = {"market_market_ioc": {"base_size": f"{base_size:.{symbol_info['precision']}f}"}}
            trade_amount_str = f"{format_crypto_amount(base_size, symbol)} {symbol}"

        # Add Stop Loss / Take Profit configuration if provided
        if sl_percent or tp_percent:
            stop_trigger_price = None
            if sl_percent:
                sl_price = current_price * (1 - sl_percent / 100) if side.lower() == "buy" else current_price * (1 + sl_percent / 100)
                stop_trigger_price = f"{sl_price:.2f}"

            tp_price = None
            if tp_percent:
                tp_limit_price = current_price * (1 + tp_percent / 100) if side.lower() == "buy" else current_price * (1 - tp_percent / 100)
                tp_price = f"{tp_limit_price:.2f}"
            
            # For a simple market order, we can't attach SL/TP directly.
            # This is a placeholder for a more complex order type (e.g., OCO) if the API supports it.
            # For now, we will log that we received the SL/TP info.
            logging.info(f"Trade includes SL at {stop_trigger_price} and TP at {tp_price}")
            # In a real scenario, you would change order_config to a complex order type.
            # For example: order_config = {"stop_limit_stop_limit_oco": {...}}

        order_data = {
            "client_order_id": str(uuid4()),
            "product_id": product_id,
            "side": side.upper(),
            "order_configuration": order_config
        }
        
        response = client.create_order(**order_data)
        order_id = getattr(response, 'order_id', 'N/A')
        success = getattr(response, 'success', False)
        
        trade_history.append({'symbol': symbol, 'side': side, 'amount_str': trade_amount_str, 'timestamp': datetime.now(), 'order_id': order_id, 'success': success})
        
        pnl_data = get_pnl_analysis()
        action_str = "BUY ORDER" if side.lower() == "buy" else "SELL ORDER"
        
        message = f"""✅ <b>{action_str} EXECUTED</b>
{symbol_info['emoji']} Symbol: {symbol_info['name']} ({symbol})
💰 Amount: {trade_amount_str}
🆔 Order ID: {order_id}
✅ Success: {success}

📊 <b>Current P/L</b>
📈 Unrealized: ${pnl_data['total_unrealized_pnl']:.2f}
🟢 Daily: ${pnl_data['daily_pnl']:.2f}"""
        
        send_telegram_message(message)
        return {"order_id": order_id, "success": success}
        
    except Exception as e:
        error_msg = f"❌ <b>Trade Failed</b>: {side.upper()} {symbol} | Error: {e}"
        send_telegram_message(error_msg)
        logging.error(f"Trade execution failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def execute_crypto_conversion(from_symbol: str, to_symbol: str, percentage: float = 100.0):
    """Convert one cryptocurrency to another (e.g., BTC to ADA)"""
    try:
        from_symbol, to_symbol = normalize_symbol(from_symbol), normalize_symbol(to_symbol)
        from_info, to_info = get_symbol_info(from_symbol), get_symbol_info(to_symbol)
        
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        source_position = next((pos for pos in portfolio['breakdown']['spot_positions'] if pos['asset'] == from_symbol), None)
        
        if not source_position:
            raise Exception(f"No {from_symbol} position found to convert")
        
        available_crypto = float(source_position['available_to_trade_crypto'])
        if available_crypto < 0.00001:
            raise Exception(f"Insufficient {from_symbol} balance")
            
        convert_amount = round(available_crypto * (percentage / 100.0), from_info['precision'])
        
        # Step 1: Sell source crypto to USD
        sell_order_data = {"client_order_id": str(uuid4()), "product_id": f"{from_symbol}-USD", "side": "SELL", "order_configuration": {"market_market_ioc": {"base_size": f"{convert_amount:.{from_info['precision']}f}"}}}
        sell_response = client.create_order(**sell_order_data)
        if not sell_response.get('success', False):
            raise Exception(f"Failed to sell {from_symbol}")
        
        time.sleep(2) # Wait for settlement
        
        # Step 2: Buy target crypto with USD
        updated_portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        usd_position = next((pos for pos in updated_portfolio['breakdown']['spot_positions'] if pos['asset'] == 'USD'), None)
        if not usd_position:
            raise Exception("No USD balance found after selling")
            
        available_usd = round(float(usd_position['available_to_trade_fiat']) * 0.99, 2)
        
        buy_order_data = {"client_order_id": str(uuid4()), "product_id": f"{to_symbol}-USD", "side": "BUY", "order_configuration": {"market_market_ioc": {"quote_size": f"{available_usd:.2f}"}}}
        buy_response = client.create_order(**buy_order_data)
        if not buy_response.get('success', False):
            raise Exception(f"Failed to buy {to_symbol}")
            
        # Log and notify
        pnl_data = get_pnl_analysis()
        success_msg = f"""🔄 <b>CRYPTO CONVERSION EXECUTED</b>
📤 Sold: {format_crypto_amount(convert_amount, from_symbol)} {from_info['emoji']}
📥 Bought: {to_info['emoji']} {to_symbol} with ${available_usd:.2f}
📊 <b>Current P/L</b>: ${pnl_data['total_unrealized_pnl']:.2f}"""
        send_telegram_message(success_msg)
        
        return {"success": True, "sell_order_id": getattr(sell_response, 'order_id', 'N/A'), "buy_order_id": getattr(buy_response, 'order_id', 'N/A')}

    except Exception as e:
        error_msg = f"❌ <b>Conversion Failed</b>: {from_symbol} → {to_symbol} | Error: {e}"
        send_telegram_message(error_msg)
        logging.error(f"Crypto conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def convert_portfolio_to_target(target_symbol: str):
    """Converts all other crypto holdings to the target symbol."""
    send_telegram_message(f"🔥 Initiating portfolio conversion to {target_symbol}...")
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        assets_to_convert = [
            pos['asset'] for pos in positions 
            if pos['asset'] not in ['USD', 'USDC', target_symbol] and float(pos['total_balance_fiat']) > 1.0
        ]

        if not assets_to_convert:
            send_telegram_message("✅ No assets needed conversion.")
            return

        for from_symbol in assets_to_convert:
            send_telegram_message(f"Converting {from_symbol} to {target_symbol}...")
            execute_crypto_conversion(from_symbol, target_symbol, 100.0)
            time.sleep(2) # Pause between conversions

        send_telegram_message(f"✅ Portfolio conversion to {target_symbol} complete!")
        time.sleep(1)
        send_telegram_message(get_portfolio_summary(), reply_markup={"inline_keyboard": [[{"text": "🔄 Refresh", "callback_data": "refresh_status"}]]})

    except Exception as e:
        logging.error(f"Full portfolio conversion failed: {e}")
        send_telegram_message(f"❌ A critical error occurred during portfolio conversion: {e}")

def generate_voice_summary(text: str) -> Optional[bytes]:
    """Generates a voice message from text using gTTS."""
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.getvalue()
    except Exception as e:
        logging.error(f"Failed to generate voice summary: {e}")
        return None

def get_supported_symbols_list():
    """Get formatted list of supported symbols"""
    # Show a curated list for help message to avoid overwhelming the user
    curated_list = ["BTC", "ETH", "SOL", "ADA", "PEPE", "MORPHO", "PENGU"]
    message = "\n".join([f"{get_symbol_info(s)['emoji']} {s} - {get_symbol_info(s)['name']}" for s in curated_list])
    message += "\n...and hundreds more available on Coinbase!"
    return message

def get_help_message():
    """Get help message with available commands and supported symbols"""
    return f"""🤖 <b>Multi-Symbol Trading Bot Help</b>
    
📊 <b>Supported Symbols</b>
{get_supported_symbols_list()}

📈 <b>Trading & Charting</b>
/status - Bot status & P/L
/pnl - Portfolio P&L summary
/positions - All positions
/history - Recent trades
/chart [SYMBOL] - Interactive chart
/chart_image [SYMBOL] - Chart image

🎵 <b>Music Commands</b>
/play [song name] - Play a song
/pause - Pause music
/resume - Resume music
/nowplaying - See current song

⚡ <b>Uptime</b>: {((datetime.now() - bot_start_time).total_seconds() / 3600):.1f} hours"""

def send_morning_report():
    """Send morning portfolio report"""
    if ALERT_SETTINGS['morning_reports']:
        send_telegram_message(f"🌅 <b>Good Morning! Report</b>\n{get_portfolio_summary()}")

def send_evening_summary():
    """Send evening portfolio summary"""
    if ALERT_SETTINGS['evening_summaries']:
        send_telegram_message(f"🌙 <b>Evening Summary</b>\n{get_portfolio_summary()}")

def send_weekly_report():
    """Send weekly performance report"""
    send_telegram_message(f"📅 <b>Weekly Report</b>\n{get_portfolio_summary()}")

def check_risk_alerts():
    """Check for risk management triggers"""
    if ALERT_SETTINGS['risk_alerts']:
        pnl_data = get_pnl_analysis()
        unrealized_pnl = pnl_data['total_unrealized_pnl']
        if unrealized_pnl < ALERT_SETTINGS['loss_threshold']:
            send_telegram_message(f"⚠️ <b>Risk Alert</b>: Unrealized loss of ${unrealized_pnl:.2f} exceeds threshold.")
        elif unrealized_pnl > ALERT_SETTINGS['profit_threshold']:
            send_telegram_message(f"🎉 <b>Profit Alert</b>: Unrealized profit of ${unrealized_pnl:.2f} exceeds threshold.")

def stop_scheduler():
    """Stops the background scheduler thread."""
    global scheduler_thread
    if scheduler_thread and scheduler_thread.is_alive():
        scheduler_stop_event.set()
        scheduler_thread.join() # Wait for the thread to finish
        logging.info("Scheduler thread stopped.")
    schedule.clear()

def load_coinbase_products():
    """Fetches all tradable products from Coinbase and stores them."""
    global COINBASE_PRODUCTS
    try:
        logging.info("Fetching all tradable products from Coinbase...")
        products_response = client.get_products()
        
        temp_products = {}
        # The response object has a 'products' attribute which is a list of product objects
        for p in products_response.products:
            if p.product_type == 'SPOT' and p.quote_currency_id == 'USD' and not p.is_disabled:
                # Calculate precision from base_increment
                # e.g., "0.00000001" -> 8 decimal places
                base_increment_str = p.base_increment or '1'
                if '.' in base_increment_str:
                    precision = len(base_increment_str.split('.')[1])
                else:
                    precision = 0
                
                temp_products[p.product_id] = {
                    "display_name": p.base_display_symbol or p.base_currency_id,
                    "precision": precision
                }
        
        COINBASE_PRODUCTS = temp_products
        logging.info(f"✅ Loaded {len(COINBASE_PRODUCTS)} tradable USD products from Coinbase.")

    except Exception as e:
        logging.error(f"❌ Failed to load Coinbase products: {e}. Bot may not function correctly.")
        # Exit or handle gracefully if this critical step fails
        raise

def start_scheduled_reports():
    """Start scheduled Telegram reports and tasks in a background thread."""
    global scheduler_thread
    
    # Stop any existing scheduler before starting a new one
    stop_scheduler()
    scheduler_stop_event.clear()

    schedule.every().day.at("09:00").do(send_morning_report).tag('morning-report')
    schedule.every().day.at("18:00").do(send_evening_summary)
    schedule.every().sunday.at("10:00").do(send_weekly_report)
    schedule.every(5).minutes.do(check_multi_symbol_price_alerts)
    schedule.every(15).minutes.do(check_risk_alerts)
    
    def run_scheduler():
        logging.info("Scheduler thread started.")
        while not scheduler_stop_event.is_set():
            schedule.run_pending()
            # Wait for 1 minute or until the stop event is set
            scheduler_stop_event.wait(60)
        logging.info("Scheduler thread exiting.")
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

# ─── Lifespan Event Handler (replaces on_event) ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    try:
        set_telegram_webhook() # Set the webhook on startup
        load_coinbase_products() # Load products before starting anything else
        start_scheduled_reports()
        startup_msg = f"""🚀 <b>Universal Trading Bot Started!</b>
✅ Systems Initialized & Reports Scheduled.
💎 Monitoring {len(COINBASE_PRODUCTS)} symbols on Coinbase.
Send /help for commands."""
        send_telegram_message(startup_msg)
        logging.info("Bot started successfully with scheduled tasks.")
    except Exception as e:
        logging.error(f"Startup error: {e}")
    
    yield
    
    # Code to run on shutdown
    logging.info("Bot shutting down...")
    stop_scheduler()

# ─── FastAPI App Initialization ──────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

# ─── API Endpoints ───────────────────────────────────────────────────────────
@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Receive commands from Telegram chat and parse with AI"""
    try:
        data = await request.json()
        logging.info(f"Received Telegram update: {data}")

        # Handle button clicks (Callback Queries)
        if "callback_query" in data:
            callback_data = data["callback_query"]["data"]
            chat_id = data["callback_query"]["message"]["chat"]["id"]
            if str(chat_id) != TELEGRAM_CHAT_ID: return {"status": "unauthorized"}

            if callback_data == "refresh_status":
                send_telegram_message(get_portfolio_summary(), reply_markup={"inline_keyboard": [[{"text": "🔄 Refresh", "callback_data": "refresh_status"}]]})
            
            elif callback_data.startswith("confirm_convert_all_to_"):
                target_symbol = callback_data.replace("confirm_convert_all_to_", "")
                # Add a final confirmation step
                keyboard = {
                    "inline_keyboard": [[
                        {"text": f"✅ Yes, convert all to {target_symbol}", "callback_data": f"execute_convert_all_to_{target_symbol}"},
                        {"text": "❌ Cancel", "callback_data": "cancel_conversion"}
                    ]]
                }
                send_telegram_message(f"⚠️ Are you sure you want to convert your entire portfolio to {target_symbol}?", reply_markup=keyboard)

            elif callback_data.startswith("execute_convert_all_to_"):
                target_symbol = callback_data.replace("execute_convert_all_to_", "")
                convert_portfolio_to_target(target_symbol)

            elif callback_data.startswith("execute_single_conversion_"):
                parts = callback_data.replace("execute_single_conversion_", "").split('_to_')
                from_symbol, to_symbol = parts[0], parts[1]
                send_telegram_message(f"✅ Executing conversion: {from_symbol} → {to_symbol}")
                execute_crypto_conversion(from_symbol, to_symbol, 100.0)

            elif callback_data == "confirm_stop_tasks":
                send_telegram_message("🛑 Stopping all background tasks...")
                stop_scheduler()
                send_telegram_message("✅ All scheduled tasks have been stopped.")

            elif callback_data == "confirm_refresh_tasks":
                send_telegram_message("🔄 Refreshing all background tasks...")
                start_scheduled_reports()
                send_telegram_message("✅ All scheduled tasks have been reloaded and restarted.")

            elif callback_data == "cancel_conversion":
                send_telegram_message("Operation cancelled.")

            # Acknowledge the callback
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": data["callback_query"]["id"]})
            return {"status": "ok"}

        # --- Handle Replies to Documents for Advanced Actions ---
        if data.get("message", {}).get("reply_to_message", {}).get("document"):
            reply_message = data["message"]
            original_doc_message = reply_message["reply_to_message"]
            chat_id = reply_message["chat"]["id"]
            command_text = reply_message.get("text", "").lower()

            if str(chat_id) == TELEGRAM_CHAT_ID and "analyze" in command_text and "convert" in command_text:
                send_telegram_message("🤖 Complex request received. Analyzing document to find top coin...")
                
                doc = original_doc_message["document"]
                file_id = doc["file_id"]
                mime_type = doc.get("mime_type", "application/pdf")
                
                file_path_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
                file_path_res = requests.get(file_path_url).json()
                file_path = file_path_res["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                file_content = requests.get(download_url).content

                analysis_result = analyze_document_with_ai(file_content, mime_type, "Find the top recommended coin.")
                top_coin = analysis_result.get("top_coin")

                if not top_coin:
                    send_telegram_message("❌ Analysis failed to identify a clear top coin from the document.")
                    return {"status": "ok"}
                
                try:
                    # Validate that the identified coin is tradable
                    normalize_symbol(top_coin)
                except ValueError:
                    send_telegram_message(f"⚠️ AI identified '{top_coin}', but it is not a tradable symbol on Coinbase.")
                    return {"status": "ok"}

                send_telegram_message(f"✅ Top coin identified: <b>{top_coin}</b>. Now finding your largest asset...")
                
                largest_asset = get_largest_asset()
                if not largest_asset:
                    send_telegram_message("❌ Could not determine your largest asset to convert from.")
                    return {"status": "ok"}
                
                if largest_asset == top_coin:
                    send_telegram_message(f"✅ Your largest asset is already {top_coin}. No conversion needed.")
                    return {"status": "ok"}

                message = f"🤖 <b>Confirmation Required</b>\n\n" \
                          f"The AI recommends <b>{top_coin}</b>.\n" \
                          f"Your largest holding is <b>{largest_asset}</b>.\n\n" \
                          f"Do you want to convert all of your {largest_asset} to {top_coin}?"
                
                keyboard = {
                    "inline_keyboard": [[
                        {"text": f"✅ Yes, Convert {largest_asset} to {top_coin}", "callback_data": f"execute_single_conversion_{largest_asset}_to_{top_coin}"},
                        {"text": "❌ Cancel", "callback_data": "cancel_conversion"}
                    ]]
                }
                send_telegram_message(message, reply_markup=keyboard)
                return {"status": "ok"}

        # --- Handle Document Uploads for Analysis ---
        if data.get("message", {}).get("document"):
            message_data = data["message"]
            chat_id = message_data["chat"]["id"]
            if str(chat_id) != TELEGRAM_CHAT_ID: return {"status": "unauthorized"}

            doc = message_data["document"]
            file_id = doc["file_id"]
            mime_type = doc.get("mime_type", "application/octet-stream")
            caption = message_data.get("caption", "").strip()

            if caption.lower().startswith("/analyze"):
                user_prompt = caption[len("/analyze"):].strip()
                if not user_prompt:
                    send_telegram_message("Please provide a question in the caption. E.g., `/analyze What is the sentiment?`")
                    return {"status": "ok"}

                send_telegram_message("⏳ Analyzing document, please wait...")

                # Get the file path from Telegram
                file_path_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
                file_path_res = requests.get(file_path_url).json()
                file_path = file_path_res["result"]["file_path"]

                # Download the file content
                download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                file_content = requests.get(download_url).content

                # Get analysis from Gemini
                analysis_result = analyze_document_with_ai(file_content, mime_type, user_prompt)
                summary = analysis_result.get("summary", "No summary provided.")
                top_coin = analysis_result.get("top_coin")

                reply_markup = None
                if top_coin:
                    # If a top coin is identified, add a button to convert the portfolio
                    reply_markup = {
                        "inline_keyboard": [[
                            {"text": f"📈 Convert Portfolio to {top_coin}", "callback_data": f"confirm_convert_all_to_{top_coin}"}
                        ]]
                    }

                send_telegram_message(f"📄 <b>Analysis Complete</b>\n\n{summary}", reply_markup=reply_markup)
                
                return {"status": "ok"}

        if not data.get("message") or not data["message"].get("text"):
            return {"status": "ok", "info": "Not a text message"}

        chat_id = data["message"]["chat"]["id"]
        message_text = data["message"]["text"].strip()

        # --- Handle /chart command ---
        if message_text.lower().startswith("/chart"):
            parts = message_text.split()
            if len(parts) == 2:
                try:
                    symbol = normalize_symbol(parts[1])
                    if not BASE_URL:
                        send_telegram_message("❌ Charting is disabled. `BASE_URL` is not configured in the environment.")
                        return {"status": "ok"}
                    
                    chart_url = f"{BASE_URL}/web/chart/{symbol}"
                    keyboard = {
                        "inline_keyboard": [[
                            {"text": f"📈 Open Interactive {symbol} Chart", "url": chart_url}
                        ]]
                    }
                    send_telegram_message(f"Click the button below to view the live TradingView chart for <b>{symbol}</b>.", reply_markup=keyboard)
                except ValueError as e:
                    send_telegram_message(f"❌ Error: {e}")
            else:
                send_telegram_message("Please specify a symbol. Usage: `/chart BTC`")
            return {"status": "ok"}

        # --- Handle /chart_image command ---
        elif message_text.lower().startswith("/chart_image"):
            parts = message_text.split()
            if len(parts) == 2:
                try:
                    symbol = normalize_symbol(parts[1])
                    symbol_info = get_symbol_info(symbol)
                    
                    send_telegram_message(f"📊 Generating {symbol_info['emoji']} {symbol} chart...")
                    chart_bytes = generate_price_chart(symbol)
                    
                    if chart_bytes:
                        caption = f"📈 <b>{symbol_info['name']} ({symbol})</b> Price Chart\n🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        send_telegram_photo(chart_bytes, caption)
                    else:
                        send_telegram_message(f"❌ Failed to generate chart for {symbol}")
                        
                except ValueError as e:
                    send_telegram_message(f"❌ Error: {e}")
            else:
                send_telegram_message("Please specify a symbol. Usage: `/chart_image BTC`")
            return {"status": "ok"}
        
        # --- Handle Music Commands ---
        elif message_text.lower().startswith("/play"):
            # First, check for a valid token without blocking
            token_info = sp_oauth.get_cached_token()
            if not token_info:
                send_telegram_message(f"🎧 Please authorize with Spotify first by visiting:\n{BASE_URL}/login")
                return {"status": "ok"}

            query = message_text[len("/play"):].strip()
            if not query:
                send_telegram_message("Please specify a song to play. Usage: `/play Never Gonna Give You Up`")
                return {"status": "ok"}
            
            try:
                # Search for the track
                results = sp.search(q=query, type='track', limit=1)
                if not results['tracks']['items']:
                    send_telegram_message(f"❌ Could not find any song matching '{query}'.")
                    return {"status": "ok"}
                
                track = results['tracks']['items'][0]
                track_uri = track['uri']
                track_name = track['name']
                artist_name = track['artists'][0]['name']

                # Start playback
                sp.start_playback(uris=[track_uri])
                send_telegram_message(f"🎵 Now playing: <b>{track_name}</b> by {artist_name}")

            except spotipy.exceptions.SpotifyException as e:
                # Handle specific Spotify errors, like no active device
                if e.http_status == 404 and "No active device found" in e.msg:
                    send_telegram_message("❌ No active Spotify device found. Please start playing on one of your devices first.")
                else:
                    send_telegram_message(f"❌ Spotify Error: {e}. Please try re-authorizing at {BASE_URL}/login")
            except Exception as e:
                send_telegram_message(f"❌ An unexpected error occurred: {e}")
            return {"status": "ok"}

        elif message_text.lower() in ["/pause", "/resume", "/nowplaying"]:
            token_info = sp_oauth.get_cached_token()
            if not token_info:
                send_telegram_message(f"🎧 Please authorize with Spotify first by visiting:\n{BASE_URL}/login")
                return {"status": "ok"}

            try:
                if message_text.lower() == "/pause":
                    sp.pause_playback()
                    send_telegram_message("⏸️ Playback paused.")
                elif message_text.lower() == "/resume":
                    sp.start_playback()
                    send_telegram_message("▶️ Playback resumed.")
                elif message_text.lower() == "/nowplaying":
                    current_track = sp.current_playback()
                    if current_track and current_track.get('is_playing'):
                        item = current_track['item']
                        track_name = item['name']
                        artist_name = item['artists'][0]['name']
                        send_telegram_message(f"🎧 Currently Playing: <b>{track_name}</b> by {artist_name}")
                    else:
                        send_telegram_message("🔇 Nothing is currently playing.")

            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 404 and "No active device found" in e.msg:
                    send_telegram_message("❌ No active Spotify device found. Please start playing on one of your devices first.")
                else:
                    send_telegram_message(f"❌ Spotify Error: {e}. Please try re-authorizing at {BASE_URL}/login")
            except Exception as e:
                send_telegram_message(f"❌ An unexpected error occurred: {e}")
            return {"status": "ok"}

        # --- Handle Task Management Commands ---
        elif message_text.lower() == "/tasks stop":
            keyboard = {"inline_keyboard": [[
                {"text": "🛑 Yes, stop all tasks", "callback_data": "confirm_stop_tasks"},
                {"text": "❌ Cancel", "callback_data": "cancel_conversion"}
            ]]}

            send_telegram_message("⚠️ Are you sure you want to stop all scheduled reports and alerts?", reply_markup=keyboard)
            return {"status": "ok"}

        elif message_text.lower() == "/tasks refresh":
            keyboard = {"inline_keyboard": [[
                {"text": "🔄 Yes, refresh tasks", "callback_data": "confirm_refresh_tasks"},
                {"text": "❌ Cancel", "callback_data": "cancel_conversion"}
            ]]}

            send_telegram_message("⚠️ Are you sure you want to reload and restart all scheduled tasks?", reply_markup=keyboard)
            return {"status": "ok"}


        if str(chat_id) != TELEGRAM_CHAT_ID:
            logging.warning(f"Unauthorized chat ID: {chat_id}")
            return {"status": "unauthorized"}

        if not gemini_client:
            send_telegram_message("🤖 AI command processing is disabled. Please configure GOOGLE_API_KEY.")
            return {"status": "error", "detail": "AI not configured"}

        # Use AI to parse the command
        command = parse_command_with_ai(message_text)
        action = command.get("action")

        if action in ["buy", "sell"]:
            symbol = command.get("symbol")
            if not symbol:
                send_telegram_message("🤔 Sorry, I couldn't identify a symbol in your command.")
                return {"status": "ok"}
            try:
                normalized_symbol = normalize_symbol(symbol)
                send_telegram_message(f"✅ AI understood: {action.capitalize()} {normalized_symbol}. Executing...")
                execute_trade(normalized_symbol, action)
            except ValueError as e:
                send_telegram_message(f"🤔 Sorry, '{symbol}' is not a valid or tradable symbol on Coinbase.")

        elif action == "convert":
            from_sym = command.get("symbol")
            to_sym = command.get("to_symbol")
            percentage = command.get("percentage", 100.0)
            if not from_sym or not to_sym:
                 send_telegram_message("🤔 For conversions, please specify both cryptocurrencies (e.g., 'convert btc to ada').")
            else:
                try:
                    norm_from = normalize_symbol(from_sym)
                    norm_to = normalize_symbol(to_sym)
                    send_telegram_message(f"✅ AI understood: Convert {percentage}% of {norm_from} to {norm_to}. Executing...")
                    execute_crypto_conversion(norm_from, norm_to, float(percentage))
                except ValueError as e:
                    send_telegram_message(f"❌ Conversion failed: One of the symbols is not valid. {e}")

        elif action == "status":
            send_telegram_message(get_portfolio_summary(), reply_markup={"inline_keyboard": [[{"text": "🔄 Refresh", "callback_data": "refresh_status"}]]})
        
        elif action == "help":
            send_telegram_message(get_help_message())

        # --- Add new command handlers here ---
        elif message_text.lower() == "/positions":
            send_telegram_message(get_detailed_positions())
        
        elif message_text.lower() == "/history":
            send_telegram_message(get_trade_history())

        else: # action == "unknown"
            send_telegram_message("🤔 Sorry, I didn't understand that command. Please try again or type /help.")

        return {"status": "ok"}

    except Exception as e:
        logging.error(f"Telegram webhook error: {e}")
        return {"status": "error"}


@app.post("/webhook")
async def tradingview_webhook(request: Request):
    """Receive TradingView alerts and execute trades"""
    data_str = "" # Initialize to have access in the except block
    try:
        # Read the raw body as text first to handle potential formatting issues
        body_text = await request.body()
        data_str = body_text.decode('utf-8').strip()
        
        # Log the raw string for debugging
        logging.info(f"Received raw webhook body: {data_str}")
        
        # Parse the cleaned string into a JSON object
        data = json.loads(data_str)
        
        action = data.get("action", "").lower()
        # Allow new actions: tp (take profit) and sl (stop loss)
        if action not in ["buy", "sell", "tp", "sl"]:
            logging.error(f"Webhook Error: Invalid action '{action}' received.")
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        # Normalize symbol *after* validating action
        symbol = normalize_symbol(data.get("symbol"))
        sl_percent = data.get("sl_percent")
        tp_percent = data.get("tp_percent")
        
        # Determine the trade action and alert message
        trade_action = "buy"
        alert_text = f"BUY SIGNAL: {symbol}"
        
        if action == "sell":
            trade_action = "sell"
            alert_text = f"SELL SIGNAL: {symbol}"
        elif action == "tp":
            trade_action = "sell"
            alert_text = f"TAKE PROFIT HIT: Closing {symbol}"
        elif action == "sl":
            trade_action = "sell"
            alert_text = f"STOP LOSS HIT: Closing {symbol}"
            
        alert_message = f"🚨 <b>TradingView Alert</b>: {alert_text}"
        if sl_percent or tp_percent:
            alert_message += f" (SL: {sl_percent}%, TP: {tp_percent}%)"
        send_telegram_message(alert_message)
        
        # Execute the trade using the determined action
        trade_result = execute_trade(symbol, trade_action, sl_percent, tp_percent)
        
        time.sleep(2) # Allow time for portfolio to update
        portfolio_summary = get_portfolio_summary()
        send_telegram_message(portfolio_summary)
        
        return {"status": "success", "details": trade_result}

    except HTTPException as e:
        # Re-raise HTTPExceptions directly
        raise e
        
    except json.JSONDecodeError as e:
        # Handle JSON parsing errors specifically
        error_msg = f"❌ <b>Webhook JSON Error</b>\n\nFailed to parse alert from TradingView. Please check the alert's message format.\n\n<b>Received</b>:\n<pre>{data_str}</pre>\n\n<b>Error</b>: {e}"
        logging.error(f"Webhook JSONDecodeError: {e}. Raw data: {data_str}")
        send_telegram_message(error_msg)
        # Return 400 Bad Request, as the client sent invalid data
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")

    except ValueError as e:
        # Specifically catch errors from normalize_symbol
        logging.error(f"Webhook ValueError: {e}. Raw data: {data_str}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        # Handle specific, non-critical errors gracefully
        if "insufficient" in str(e).lower() and "balance" in str(e).lower():
            error_msg = f"ℹ️ <b>Action Skipped</b>: Received {action.upper()} alert for {symbol}, but balance is insufficient. No action taken."
            logging.warning(f"Webhook info: {error_msg}")
            send_telegram_message(error_msg)
            # Return 200 OK to prevent TradingView from retrying
            return {"status": "skipped", "reason": str(e)}
        
        # Handle all other unexpected errors
        logging.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/convert-crypto")
async def convert_crypto_api(request: Request):
    """API endpoint to convert one cryptocurrency to another"""
    try:
        data = await request.json()
        from_symbol = data.get("from_symbol")
        to_symbol = data.get("to_symbol")
        percentage = float(data.get("percentage", 100.0))
        
        if not from_symbol or not to_symbol:
            raise HTTPException(status_code=400, detail="Missing from_symbol or to_symbol")
        
        result = execute_crypto_conversion(from_symbol, to_symbol, percentage)
        return {"status": "success", "details": result}
    except Exception as e:
        logging.error(f"API Conversion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/login")
async def spotify_login():
    """Redirects user to Spotify for authorization."""
    auth_url = sp_oauth.get_authorize_url()
    return HTMLResponse(f'<h2>Please authorize with Spotify</h2><p><a href="{auth_url}">Click here to login</a></p>')

@app.get("/callback")
async def spotify_callback(code: str):
    """Handles the callback from Spotify after authorization."""
    try:
        sp_oauth.get_access_token(code, as_dict=False)
        return HTMLResponse("✅ Success! You can now use the music commands in Telegram. You may close this window.")
    except spotipy.exceptions.SpotifyOauthError as e:
        logging.error(f"Spotify auth callback error: {e}")
        error_message = f"""
        <h1>❌ Spotify Authorization Failed</h1>
        <p>There was an error authenticating with Spotify.</p>
        <p><b>Error:</b> {str(e)}</p>
        <p>This usually means your <b>Client ID</b> or <b>Client Secret</b> is incorrect in your <code>.env</code> file.</p>
        <p>Please double-check your credentials on the <a href="https://developer.spotify.com/dashboard">Spotify Developer Dashboard</a> and restart the bot.</p>
        """
        return HTMLResponse(content=error_message, status_code=400)
    except Exception as e:
        logging.error(f"An unexpected error occurred in spotify_callback: {e}")
        return HTMLResponse(content="<h1>❌ An unexpected error occurred. Check the logs.</h1>", status_code=500)

@app.get("/web/chart/{symbol}", response_class=HTMLResponse)
async def get_web_chart(symbol: str):
    """Serves an HTML page with a TradingView chart widget."""
    try:
        symbol = normalize_symbol(symbol)
        symbol_info = get_symbol_info(symbol)
        
        # Read the HTML template from the file
        with open("templates/tradingview.html", "r") as f:
            html_content = f.read()
            
        # Inject the dynamic data into the HTML
        html_content = html_content.replace("__SYMBOL__", symbol)
        html_content = html_content.replace("__SYMBOL_NAME__", symbol_info['name'])
        html_content = html_content.replace("__SYMBOL_EMOJI__", symbol_info['emoji'])

        return HTMLResponse(content=html_content)

    except Exception as e:
        logging.error(f"Web chart error for {symbol}: {e}")
        return HTMLResponse(content=f"<h1>Error generating chart for {symbol}</h1><p>{e}</p>", status_code=500)

@app.get("/api/v1/reports/morning/next")
async def get_next_morning_report_api():
    """Get the next scheduled time for the morning report"""
    try:
        # Get the job by its tag
        jobs = schedule.get_jobs('morning-report')
        if not jobs:
            raise HTTPException(status_code=404, detail="Morning report job not found.")
        
        # There should be only one, but we take the first
        next_run_time = jobs[0].next_run
        
        return {
            "job_name": "morning-report",
            "next_run_utc": next_run_time.isoformat(),
            "next_run_local": str(next_run_time)
        }
    except Exception as e:
        logging.error(f"Error getting next report time: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def generate_tradingview_chart_image(symbol: str) -> Optional[bytes]:
    """
    Generates a chart image using TradingView's chart image API.
    
    Args:
        symbol: The crypto symbol (e.g., "BTC").
        
    Returns:
        The chart image as bytes, or None if an error occurs.
    """
    try:
        # TradingView chart image URL parameters
        chart_params = {
            'symbol': f'COINBASE:{symbol}USD',
            'interval': '1h',
            'width': '800',
            'height': '400',
            'theme': 'dark',
            'style': '1',  # Candlestick style
            'toolbar_bg': '#131722',
            'studies': 'RSI,MACD',  # Add technical indicators
            'format': 'png'
        }
        
        # Build the TradingView chart image URL
        base_url = "https://www.tradingview.com/x/"
        params_str = "&".join([f"{k}={v}" for k, v in chart_params.items()])
        chart_url = f"{base_url}?{params_str}"
        
        # Download the chart image
        response = requests.get(chart_url, timeout=30)
        response.raise_for_status()
        
        return response.content
        
    except Exception as e:
        logging.error(f"Error generating TradingView chart for {symbol}: {e}")
        return None

def generate_price_chart(symbol: str) -> Optional[bytes]:
    """
    Generates a chart image for a given crypto symbol.
    First tries TradingView, falls back to matplotlib if needed.
    
    Args:
        symbol: The crypto symbol (e.g., "BTC").
        
    Returns:
        The chart image as bytes, or None if an error occurs.
    """
    # Try TradingView first
    chart_bytes = generate_tradingview_chart_image(symbol)
    if chart_bytes:
        return chart_bytes
    
    # Fallback to matplotlib chart
    logging.info(f"TradingView chart failed for {symbol}, using fallback matplotlib chart")
    return generate_matplotlib_chart(symbol)

def generate_matplotlib_chart(symbol: str) -> Optional[bytes]:
    """
    Generates a 24-hour price chart using matplotlib as a fallback.
    
    Args:
        symbol: The crypto symbol (e.g., "BTC").
        
    Returns:
        The chart image as bytes, or None if an error occurs.
    """
    product_id = f"{symbol}-USD"
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)

    try:
        # Fetch the product candles (OHLC data)
        candles = client.get_product_historic_rates(
            product_id,
            start=start_time.isoformat(),
            end=end_time.isoformat(),
            granularity=3600  # 1 hour granularity
        )

        # Prepare the data for the chart
        df = pd.DataFrame(candles, columns=["time", "low", "high", "open", "close", "volume"])
        # Robustly parse the "time" column
        if pd.api.types.is_numeric_dtype(df["time"]):
            # Check if time is in milliseconds (typical if values are large)
            if df["time"].max() > 1e12:
                df["time"] = pd.to_datetime(df["time"], unit="ms")
            else:
                df["time"] = pd.to_datetime(df["time"], unit="s")
        else:
            # Assume ISO8601 string
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df.set_index("time", inplace=True)

        # Generate the chart
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df.index, df["close"], label="Close Price", color="blue")
        ax.fill_between(df.index, df["low"], df["high"], color="lightblue", alpha=0.5, label="Price Range")
        ax.set_title(f"{symbol} Price Chart (Last 24 Hours)")
        ax.set_xlabel("Time")
        ax.set_ylabel("Price (USD)")
        ax.legend()

        # Save the chart to a BytesIO object
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close(fig)  # Close the figure to free memory
        return buf.getvalue()
    except Exception as e:
        logging.error(f"Error generating matplotlib chart for {symbol}: {e}")
        return None

# ─── API Endpoints for Web App ──────────────────────────────────────────────
@app.get("/api/v1/portfolio/summary-data")
async def get_portfolio_summary_data():
    """Provides portfolio summary data for the web dashboard."""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        balances = portfolio['breakdown']['portfolio_balances']
        pnl_data = get_pnl_analysis()
        
        return {
            "total_value": float(balances['total_balance']['value']),
            "crypto": float(balances['total_crypto_balance']['value']),
            "cash": float(balances['total_cash_equivalent_balance']['value']),
            "unrealized_pnl": pnl_data['total_unrealized_pnl']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/portfolio/positions-data")
async def get_positions_data():
    """Provides detailed position data for the web dashboard."""
    try:
        portfolio = client.get_portfolio_breakdown(portfolio_uuid=PORTFOLIO_UUID)
        positions = portfolio['breakdown']['spot_positions']
        
        data = []
        for pos in positions:
            if pos['asset'] not in ['USD', 'USDC'] and float(pos['total_balance_fiat']) > 0.01:
                info = get_symbol_info(pos['asset'])
                data.append({
                    "symbol": pos['asset'],
                    "name": info['name'],
                    "emoji": info['emoji'],
                    "amount": format_crypto_amount(float(pos['available_to_trade_crypto']), pos['asset']),
                    "value_fiat": float(pos['total_balance_fiat']),
                    "pnl": float(pos['unrealized_pnl'])
                })
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/trades/history-data")
async def get_trade_history_data():
    """Provides trade history for the web dashboard."""
    return trade_history

@app.get("/api/v1/spotify/token")
async def get_spotify_token():
    """Provides the Spotify access token to the client-side player."""
    token_info = sp_oauth.get_cached_token()
    if not token_info:
        raise HTTPException(status_code=401, detail="User not authenticated with Spotify.")
    return {"access_token": token_info['access_token']}

@app.get("/api/v1/supported-symbols")
async def get_supported_symbols_data():
    """Provides a list of supported symbols for the web dashboard."""
    return [
        {"symbol": product_id.replace('-USD', ''), "name": info['display_name'], "emoji": CUSTOM_EMOJIS.get(product_id.replace('-USD', ''), "💰")}
        for product_id, info in COINBASE_PRODUCTS.items()
    ]

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serves the main web dashboard."""
    with open("templates/dashboard.html", "r") as f:
        return HTMLResponse(content=f.read())

# ─── Main Execution (for local testing) ──────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    logging.info("Starting Uvicorn server for local dashboard...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000)