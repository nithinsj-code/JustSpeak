"""
JustSpeak (ஒன்று பேசு) — FastAPI Backend
Voice-first Tamil digital literacy agent for old-age pension applications.
"""

import os
import sys
import asyncio
from pathlib import Path

# Fix for Windows asyncio subprocess / Playwright compatibility
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers.session import router as session_router


# Load .env from backend or root directory
base_dir = Path(__file__).resolve().parent
for env_path in (base_dir / ".env", base_dir.parent / ".env", base_dir / "tests" / ".env"):
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
load_dotenv()


app = FastAPI(
    title="JustSpeak API",
    description="Voice-first Tamil conversational agent for old-age pension applications",
    version="1.0.0",
)

# CORS — allow frontend origin
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(session_router)

# Mount static files (mock government site)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {
        "app": "JustSpeak (ஒன்று பேசு)",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
