"""
Supabase service — session persistence and submission logging.
"""

import os
import random
import string
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

MOCK_MODE = (
    not SUPABASE_URL
    or not SUPABASE_KEY
    or "your-project-id" in SUPABASE_URL
    or "your_supabase_anon_key" in SUPABASE_KEY
)

if MOCK_MODE:
    print("[SUPABASE] Running in MOCK MODE (using in-memory db)")

_client: Client | None = None
_mock_sessions = {}
_mock_submissions = {}
_session_languages = {}


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------

def create_session(session_id: str, language: str = "ta") -> dict:
    """Create a new session row in Supabase (or in-memory mock)."""
    now = datetime.now(timezone.utc).isoformat()
    _session_languages[session_id] = language

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
    if MOCK_MODE:
        data["language"] = language
        _mock_sessions[session_id] = data.copy()
        return data

    client = get_client()
    # Try inserting with dynamic columns first; fallback if schema doesn't have it yet
    try:
        db_payload = {**data, "language": language, "dynamic_slots": getattr(data, "dynamic_slots", [])}
        result = client.table("sessions").insert(db_payload).execute()
        ret = result.data[0] if result.data else db_payload
        ret["language"] = language
        return ret
    except Exception as e:
        # Schema might not have 'language' or 'dynamic_slots' column yet
        try:
            result = client.table("sessions").insert(data).execute()
            ret = result.data[0] if result.data else data
            ret["language"] = language
            return ret
        except Exception as inner_e:
            print(f"[SUPABASE] insert failed ({inner_e}), using in-memory session")
            data["language"] = language
            _mock_sessions[session_id] = data.copy()
            return data


def get_session(session_id: str) -> dict | None:
    """Fetch a session by ID."""
    lang = _session_languages.get(session_id, "ta")
    if MOCK_MODE:
        ret = _mock_sessions.get(session_id)
        if ret:
            ret["language"] = lang
        return ret

    try:
        client = get_client()
        result = client.table("sessions").select("*").eq("id", session_id).execute()
        if result.data:
            row = result.data[0]
            row["language"] = row.get("language") or lang
            return row
    except Exception as e:
        print(f"[SUPABASE] get_session failed ({e})")

    ret = _mock_sessions.get(session_id)
    if ret:
        ret["language"] = lang
    return ret


def update_session(session_id: str, updates: dict) -> dict:
    """Update session fields."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "language" in updates:
        _session_languages[session_id] = updates["language"]

    if MOCK_MODE:
        if session_id in _mock_sessions:
            _mock_sessions[session_id].update(updates)
            return _mock_sessions[session_id]
        return updates

    client = get_client()
    try:
        result = client.table("sessions").update(updates).eq("id", session_id).execute()
        return result.data[0] if result.data else updates
    except Exception as e:
        # Strip missing columns (language, dynamic_slots) if schema is outdated
        db_updates = {k: v for k, v in updates.items() if k not in ("language", "dynamic_slots")}
        try:
            result = client.table("sessions").update(db_updates).eq("id", session_id).execute()
            return result.data[0] if result.data else updates
        except Exception as inner_e:
            print(f"[SUPABASE] update_session fallback failed ({inner_e})")
            if session_id in _mock_sessions:
                _mock_sessions[session_id].update(updates)
            return updates


def session_to_dict(session_data) -> dict:
    """Convert a SessionData pydantic model to a dict for Supabase."""
    return {
        "state": session_data.state.value,
        "language": getattr(session_data, "language", "ta") or "ta",
        "slots": {
            k: {
                "value": v.value,
                "confidence": v.confidence,
                "attempts": v.attempts,
                "skipped": v.skipped,
            }
            for k, v in session_data.slots.items()
        },
        "dynamic_slots": getattr(session_data, "dynamic_slots", []),
        "current_slot_index": session_data.current_slot_index,
        "confirmation_index": session_data.confirmation_index,
        "retry_count": session_data.retry_count,
    }


def dict_to_session_data(data: dict):
    """Convert a Supabase row dict back to a SessionData object."""
    from models.schemas import SessionData, SlotInfo, ConversationState

    session_id = data["id"]
    lang = data.get("language") or _session_languages.get(session_id, "ta")

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
        id=session_id,
        state=ConversationState(data.get("state", "GREETING")),
        language=lang,
        slots=slots,
        dynamic_slots=data.get("dynamic_slots", []),
        current_slot_index=data.get("current_slot_index", 0),
        confirmation_index=data.get("confirmation_index", 0),
        retry_count=data.get("retry_count", 0),
        created_at=data.get("created_at"),
    )


# ---------------------------------------------------------------------------
# Submission operations
# ---------------------------------------------------------------------------


def generate_reference_number() -> str:
    """Generate a unique reference number like JS-2024-A7X9."""
    year = datetime.now().year
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"JS-{year}-{suffix}"


def create_submission(session_id: str, form_data: dict) -> str:
    """Write the final submission to Supabase. Returns reference number."""
    ref = generate_reference_number()
    data = {
        "session_id": session_id,
        "reference_number": ref,
        "form_data": form_data,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    if MOCK_MODE:
        _mock_submissions[ref] = data
        return ref

    try:
        client = get_client()
        client.table("submissions").insert(data).execute()
    except Exception as e:
        print(f"[SUPABASE] create_submission failed ({e}), saving in memory")
        _mock_submissions[ref] = data
    return ref
