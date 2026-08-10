"""
Supabase service — session persistence and submission logging.
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

def create_session(session_id: str) -> dict:
    """Create a new session row in Supabase."""
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": session_id,
        "state": "GREETING",
        "slots": {},
        "current_slot_index": 0,
        "confirmation_index": 0,
        "retry_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    result = client.table("sessions").insert(data).execute()
    return result.data[0] if result.data else data


def get_session(session_id: str) -> dict | None:
    """Fetch a session by ID."""
    client = get_client()
    result = client.table("sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None


def update_session(session_id: str, updates: dict) -> dict:
    """Update session fields."""
    client = get_client()
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = client.table("sessions").update(updates).eq("id", session_id).execute()
    return result.data[0] if result.data else updates


def session_to_dict(session_data) -> dict:
    """Convert a SessionData pydantic model to a dict for Supabase."""
    return {
        "state": session_data.state.value,
        "slots": {
            k: {
                "value": v.value,
                "confidence": v.confidence,
                "attempts": v.attempts,
                "skipped": v.skipped,
            }
            for k, v in session_data.slots.items()
        },
        "current_slot_index": session_data.current_slot_index,
        "confirmation_index": session_data.confirmation_index,
        "retry_count": session_data.retry_count,
    }


def dict_to_session_data(data: dict):
    """Convert a Supabase row dict back to a SessionData object."""
    from models.schemas import SessionData, SlotInfo, ConversationState

    slots_raw = data.get("slots", {})
    slots = {
        k: SlotInfo(
            value=v.get("value"),
            confidence=v.get("confidence"),
            attempts=v.get("attempts", 0),
            skipped=v.get("skipped", False),
        )
        for k, v in slots_raw.items()
    }

    return SessionData(
        id=data["id"],
        state=ConversationState(data.get("state", "GREETING")),
        slots=slots,
        current_slot_index=data.get("current_slot_index", 0),
        confirmation_index=data.get("confirmation_index", 0),
        retry_count=data.get("retry_count", 0),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Submission operations
# ---------------------------------------------------------------------------

import random
import string


def generate_reference_number() -> str:
    """Generate a unique reference number like JS-2024-A7X9."""
    year = datetime.now().year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"JS-{year}-{suffix}"


def create_submission(session_id: str, form_data: dict) -> str:
    """Write the final submission to Supabase. Returns reference number."""
    client = get_client()
    ref = generate_reference_number()
    data = {
        "session_id": session_id,
        "reference_number": ref,
        "form_data": form_data,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("submissions").insert(data).execute()
    return ref


# ---------------------------------------------------------------------------
# Supabase SQL schema (run this in Supabase SQL Editor)
# ---------------------------------------------------------------------------

SUPABASE_SCHEMA_SQL = """
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'GREETING',
    slots JSONB NOT NULL DEFAULT '{}',
    current_slot_index INTEGER NOT NULL DEFAULT 0,
    confirmation_index INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    reference_number TEXT NOT NULL,
    form_data JSONB NOT NULL,
    submitted_at TIMESTAMPTZ DEFAULT now()
);

-- Enable Row Level Security (allow all for now — tighten for production)
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all sessions" ON sessions FOR ALL USING (true);
CREATE POLICY "Allow all submissions" ON submissions FOR ALL USING (true);
"""
