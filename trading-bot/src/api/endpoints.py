from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.coinbase_service import execute_trade, get_portfolio_summary
from services.telegram_service import send_telegram_message

router = APIRouter()

class TradeRequest(BaseModel):
    symbol: str
    action: str

@router.post("/trade")
async def trade(request: TradeRequest):
    try:
        result = execute_trade(request.symbol, request.action)
        return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/portfolio")
async def portfolio_summary():
    try:
        summary = get_portfolio_summary()
        return {"status": "success", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))