# app/main.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv

# load .env located in the same folder as this file (app/.env)
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

from .api import router as api_router
from .ws import websocket_endpoint

app = FastAPI(title="CodeFixAI")

# CORS for frontend dev - adjust origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API router at /api
app.include_router(api_router, prefix="/api")

# WebSocket route
@app.websocket("/ws/diagnose")
async def ws_diagnose(websocket: WebSocket):
    await websocket_endpoint(websocket)
