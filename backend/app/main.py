from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ml import router as ml_router
from app.api.backtests import router as backtests_router
from app.api.portfolios import router as portfolios_router
from app.api.stocks import router as stocks_router
from app.api.universes import router as universes_router
from app.api.users import router as users_router

app = FastAPI(
    title="PortfolioPilot API",
    description="Backend API for the PortfolioPilot portfolio management platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:3000",
        "http://192.168.50.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(portfolios_router)
app.include_router(stocks_router)
app.include_router(universes_router)
app.include_router(ml_router)
app.include_router(backtests_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
