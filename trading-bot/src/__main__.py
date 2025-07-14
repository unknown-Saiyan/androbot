from fastapi import FastAPI
from src.api.endpoints import router as api_router
from src.core.scheduler import start_scheduled_reports
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    start_scheduled_reports()

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))