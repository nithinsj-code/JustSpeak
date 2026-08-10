"""
JustSpeak (ஒன்று பேசு) — FastAPI Backend
Voice-first Tamil digital literacy agent for old-age pension applications.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.session import router as session_router

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
    allow_origins=[FRONTEND_ORIGIN, "https://just-speak.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(session_router)


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
