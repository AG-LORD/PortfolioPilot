from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.portfolios import router as portfolios_router
from app.api.users import router as users_router

app = FastAPI(
    title="PortfolioPilot API",
    description="Backend API for the PortfolioPilot portfolio management platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(portfolios_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
