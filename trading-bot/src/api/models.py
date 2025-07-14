from pydantic import BaseModel
from typing import List, Optional

class TradeRequest(BaseModel):
    symbol: str
    action: str  # "buy" or "sell"
    amount: Optional[float] = None  # Amount to buy/sell, if applicable

class TradeResponse(BaseModel):
    order_id: str
    success: bool
    message: Optional[str] = None

class PortfolioSummary(BaseModel):
    total_value: float
    cash: float
    crypto: float
    top_positions: List[str]
    unrealized_pnl: float
    daily_pnl: float
    updated_at: str

class PriceAlert(BaseModel):
    symbol: str
    current_price: float
    price_change: float
    alert_message: str

class RiskAlert(BaseModel):
    unrealized_loss: float
    message: str