# 🤖 AndroBot - AI-Powered Cryptocurrency Trading Bot

A sophisticated, multi-symbol cryptocurrency trading bot that combines Coinbase trading, AI-powered command processing, and automated portfolio management through Telegram integration.

## ✨ Features

### 🎯 Core Trading Features

- **Multi-Symbol Trading**: Support for BTC, ETH, MORPHO, PEPE, ADA, SOL, and PENGU
- **AI Command Processing**: Natural language command parsing using Google's Gemini AI
- **Automated Trade Execution**: Market orders with dynamic position sizing
- **Crypto-to-Crypto Conversion**: Direct conversion between cryptocurrencies
- **Portfolio Rebalancing**: Convert entire portfolio to target cryptocurrency

### 📊 Analytics & Monitoring

- **Real-time P&L Tracking**: Unrealized profits/losses with daily and yearly analysis
- **Interactive Charts**: TradingView integration with web-based charting
- **Chart Images**: Generate and send chart images directly to Telegram
- **Price Alerts**: Automated notifications for significant price movements
- **Risk Management**: Configurable loss/profit thresholds

### 🤖 AI-Powered Features

- **Document Analysis**: Upload PDFs/documents for AI-powered market analysis
- **Smart Command Parsing**: Natural language to structured trading commands
- **Top Coin Identification**: AI extracts recommended cryptocurrencies from reports
- **Automated Decision Making**: AI suggests trades based on document analysis

### 📱 Telegram Integration

- **Command Interface**: Full trading control via Telegram commands
- **Interactive Buttons**: Confirm trades and actions with inline keyboards
- **Real-time Notifications**: Trade confirmations, alerts, and reports
- **File Upload Support**: Analyze market reports and research documents

### � Scheduled Automation

- **Morning Reports**: Daily portfolio summaries at 9:00 AM
- **Evening Summaries**: End-of-day performance reports at 6:00 PM
- **Weekly Reports**: Comprehensive weekly analysis every Sunday
- **Price Alerts**: Price alerts every 5 minutes
- **Risk Alerts**: Automatic notifications when thresholds are breached

### 🌐 Web Dashboard

- **Interactive Interface**: Web-based portfolio management
- **Real-time Data**: Live portfolio values and positions
- **Trade History**: Complete transaction history
- **Chart Integration**: Embedded TradingView charts

## 🛠️ Technology Stack

- **Backend**: FastAPI (Python)
- **Trading API**: Coinbase Advanced Trading API
- **AI Engine**: Google Gemini 1.5 Flash
- **Messaging**: Telegram Bot API
- **Charting**: TradingView + Matplotlib
- **Scheduling**: Python Schedule
- **Data Processing**: Pandas
- **Security**: Cryptography library for API key handling

## 📋 Prerequisites

- Python 3.8+
- Coinbase Advanced Trading account
- Telegram Bot Token
- Google AI Studio API key
- Valid SSL certificate (for webhooks)

## ⚙️ Installation

1. **Clone the repository**

```bash
git clone <repository-url>
cd androbot
```

1. **Install dependencies**

```bash
pip install -r requirements.txt
```

1. **Set up environment variables**

Create a `.env` file with the following:

```env
# Coinbase API Configuration
COINBASE_API_KEY=your_coinbase_api_key
COINBASE_API_SECRET=your_coinbase_private_key

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Google AI Configuration
GOOGLE_API_KEY=your_google_ai_api_key

# Web Dashboard Configuration
BASE_URL=https://yourdomain.com

# Portfolio Configuration
PORTFOLIO_UUID=your_portfolio_uuid
```

1. **Create HTML templates**

Create a `templates/` directory with:

- `dashboard.html` - Main web dashboard
- `tradingview.html` - Chart display page

1. **Run the application**

```bash
python main.py
```

## 🚀 Usage

### Telegram Commands

#### Basic Trading

- `/help` - Show all available commands
- `/status` - Portfolio summary with P&L
- `/positions` - Detailed position breakdown
- `/history` - Recent trade history

#### Chart Commands

- `/chart BTC` - Interactive TradingView chart
- `/chart_image ETH` - Generate chart image

#### Conversion Commands

- `/convert-crypto BTC ADA 50` - Convert 50% of BTC to ADA

#### Task Management

- `/tasks stop` - Stop all scheduled tasks
- `/tasks refresh` - Restart scheduled tasks

#### Natural Language Trading

Send messages like:

- "Buy Bitcoin"
- "Sell all my Ethereum"
- "Convert my BTC to ADA"
- "Show me my portfolio status"

### Document Analysis

1. Upload a PDF or document to Telegram
2. Add caption: `/analyze What is the market sentiment?`
3. Bot analyzes document and provides insights
4. If a top coin is identified, get conversion options

### TradingView Webhook Integration

Configure TradingView alerts to send POST requests to:

```text
https://yourdomain.com/webhook
```

JSON payload format:

```json
{
  "action": "buy",
  "symbol": "BTC",
  "sl_percent": 5.0,
  "tp_percent": 10.0
}
```

Supported actions: `buy`, `sell`, `tp` (take profit), `sl` (stop loss)

### Web Dashboard

Access the dashboard at: `https://yourdomain.com/`

Features:

- Real-time portfolio values
- Position breakdown
- Trade history
- Interactive charts

## 🪙 Supported Cryptocurrencies

| Symbol | Name | Emoji |
|--------|------|-------|
| BTC | Bitcoin | ₿ |
| ETH | Ethereum | 🔷 |
| MORPHO | Morpho | 🦋 |
| PEPE | Pepe | 🐸 |
| ADA | Cardano | 🔵 |
| SOL | Solana | 🟣 |
| PENGU | Pengu | 🐧 |

## ⚡ API Endpoints

### Trading Endpoints

- `POST /webhook` - TradingView webhook receiver
- `POST /convert-crypto` - Cryptocurrency conversion
- `POST /btc-to-ada` - Quick BTC to ADA conversion

### Data Endpoints

- `GET /api/v1/portfolio/summary-data` - Portfolio summary
- `GET /api/v1/portfolio/positions-data` - Position details
- `GET /api/v1/trades/history-data` - Trade history
- `GET /api/v1/supported-symbols` - Available symbols

### Web Interface

- `GET /` - Main dashboard
- `GET /web/chart/{symbol}` - Interactive chart page

## 🔧 Configuration

### Alert Settings

Customize in the `ALERT_SETTINGS` dictionary:

```python
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
```

### Scheduled Tasks

- Morning reports: 9:00 AM daily
- Evening summaries: 6:00 PM daily
- Weekly reports: 10:00 AM Sundays
- Price alerts: Every 5 minutes
- Risk checks: Every 15 minutes

## 🛡️ Security Features

- **API Key Encryption**: Secure handling of Coinbase private keys
- **Chat ID Validation**: Telegram commands restricted to authorized users
- **Input Validation**: Symbol validation and error handling
- **Rate Limiting**: Coinbase API rate limit compliance

## 🔍 Error Handling

- Comprehensive logging for all operations
- Graceful degradation when services are unavailable
- User-friendly error messages via Telegram
- Automatic retry mechanisms for failed operations

## 📈 Risk Management

- **Position Sizing**: Dynamic allocation based on available balance
- **Loss Thresholds**: Configurable maximum loss alerts
- **Profit Taking**: Automated profit threshold notifications
- **Balance Validation**: Pre-trade balance checks

## 🚨 Important Notes

⚠️ **Trading Risk**: Cryptocurrency trading involves substantial risk. Use at your own discretion.

⚠️ **API Security**: Never share your API keys or commit them to version control.

⚠️ **Testing**: Thoroughly test with small amounts before deploying with significant funds.

⚠️ **Monitoring**: Regularly monitor bot activity and performance.

## 📦 Dependencies

Required packages (install via `pip install -r requirements.txt`):

```text
fastapi==0.104.1
uvicorn==0.24.0
python-dotenv==1.0.0
coinbase==0.1.0
requests==2.31.0
schedule==1.2.0
google-generativeai==0.3.2
pandas==2.1.3
matplotlib==3.8.2
cryptography==41.0.7
```

## 📝 License

This project is provided as-is for educational purposes. Use responsibly.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📞 Support

For issues and questions:

1. Check the logs for error details
2. Verify environment variable configuration
3. Ensure all API keys are valid and have proper permissions

---

**⚡ Built with FastAPI, powered by AI, secured by design.**
