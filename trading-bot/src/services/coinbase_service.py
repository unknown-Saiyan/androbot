from coinbase.wallet.client import Client
import os

class CoinbaseService:
    def __init__(self):
        self.api_key = os.getenv("COINBASE_API_KEY")
        self.api_secret = os.getenv("COINBASE_API_SECRET")
        self.client = Client(self.api_key, self.api_secret)

    def get_account_balance(self):
        accounts = self.client.get_accounts()
        return {account['name']: account['balance'] for account in accounts['data']}

    def buy_crypto(self, amount, currency):
        order = self.client.buy(amount=amount, currency=currency)
        return order

    def sell_crypto(self, amount, currency):
        order = self.client.sell(amount=amount, currency=currency)
        return order

    def get_transactions(self, account_id):
        transactions = self.client.get_transactions(account_id)
        return transactions['data']

    def get_price(self, currency_pair):
        price = self.client.get_spot_price(currency_pair=currency_pair)
        return price['amount']