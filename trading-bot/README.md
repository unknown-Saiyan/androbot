# Trading Bot

## Overview
This trading bot is designed to interact with the Coinbase and Telegram APIs to facilitate automated trading based on alerts from TradingView. It provides functionalities for buying, selling, and converting cryptocurrencies, as well as sending notifications to users via Telegram.

## Project Structure
```
trading-bot
├── src
│   ├── api
│   │   ├── __init__.py
│   │   ├── endpoints.py
│   │   └── models.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── scheduler.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── coinbase_service.py
│   │   └── telegram_service.py
│   └── __main__.py
├── .env
├── requirements.txt
└── README.md
```

## Installation
1. Clone the repository:
   ```
   git clone <repository-url>
   cd trading-bot
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Set up your environment variables in the `.env` file. You will need to provide your Coinbase API key, secret, and Telegram bot token.

## Usage
To run the trading bot, execute the following command:
```
python -m src
```

The bot will start listening for TradingView alerts and execute trades based on the configured logic.

## Features
- Automated trading based on TradingView alerts.
- Integration with Coinbase for cryptocurrency transactions.
- Notifications sent to users via Telegram.
- Scheduled reports and alerts for portfolio management.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.