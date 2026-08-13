from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class ConversationState(str, Enum):
    GREETING = "GREETING"
    INTENT_CAPTURE = "INTENT_CAPTURE"
    SLOT_FILLING = "SLOT_FILLING"
    CONFIRMATION = "CONFIRMATION"
    SUBMIT = "SUBMIT"
    DONE = "DONE"


class SlotInfo(BaseModel):
    value: Optional[str] = None
    confidence: Optional[str] = None  # "high" | "low" | None
    attempts: int = 0
    skipped: bool = False


class SessionData(BaseModel):
    id: str
    state: ConversationState = ConversationState.GREETING
    language: str = "ta"  # "ta" | "en"
    slots: dict[str, SlotInfo] = {}
    current_slot_index: int = 0
    confirmation_index: int = 0  # which slot we're confirming
    retry_count: int = 0         # retries on current slot
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class StartSessionResponse(BaseModel):
    session_id: str
    audio_base64: str          # base64-encoded greeting audio
    state: str
    language: str = "ta"


class TurnRequest(BaseModel):
    """Used when sending text turns (for testing); real turns use multipart audio."""
    text_input: Optional[str] = None


class TurnResponse(BaseModel):
    audio_base64: str          # base64-encoded agent audio response
    transcript: str            # user's transcribed speech (debug only)
    agent_text: str            # agent's text response (debug only)
    state: str
    language: str = "ta"
    current_slot: Optional[str]
    slots: dict[str, Any]
    confidence: Optional[str]


class SubmitResponse(BaseModel):
    reference_number: str
    message: str
    audio_base64: str          # spoken reference number confirmation


class DebugResponse(BaseModel):
    session_id: str
    state: str
    language: str = "ta"
    current_slot: Optional[str]
    slots: dict[str, Any]
    retry_count: int
    confirmation_index: int
