"""
Session router — all conversation endpoints.
"""

import base64
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from models.schemas import (
    ConversationState,
    DebugResponse,
    SessionData,
    SlotInfo,
    StartSessionResponse,
    SubmitResponse,
    TurnResponse,
)
from services import gemini_service as gemini
from services import state_machine as sm
from services import supabase_service as db

router = APIRouter(prefix="/session", tags=["session"])


# ---------------------------------------------------------------------------
# POST /session/start
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StartSessionResponse)
async def start_session():
    """Create a new session and return the greeting audio."""
    session_id = str(uuid.uuid4())

    # Create session in Supabase
    db.create_session(session_id)

    # Build greeting audio
    greeting_audio = await gemini.synthesize_speech(gemini.GREETING_TEXT)
    audio_b64 = gemini.audio_to_base64(greeting_audio)

    return StartSessionResponse(
        session_id=session_id,
        audio_base64=audio_b64,
        state=ConversationState.GREETING.value,
    )


# ---------------------------------------------------------------------------
# POST /session/{id}/turn
# ---------------------------------------------------------------------------

@router.post("/{session_id}/turn", response_model=TurnResponse)
async def process_turn(
    session_id: str,
    audio: Optional[UploadFile] = File(None),
    text_input: Optional[str] = Form(None),
):
    """
    Accept audio blob (or text for testing), advance state machine, return agent response.
    """
    # Load session
    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")

    session = db.dict_to_session_data(session_row)

    transcript = ""
    extracted_value = ""
    confidence = "high"

    # --- Read audio or text ---
    if audio:
        audio_bytes = await audio.read()
        mime_type = audio.content_type or "audio/webm"
    elif text_input:
        audio_bytes = None
        transcript = text_input
    else:
        raise HTTPException(status_code=400, detail="Provide either audio or text_input")

    # =========================================================================
    # STATE: GREETING → INTENT_CAPTURE
    # =========================================================================
    if session.state == ConversationState.GREETING:
        # Transition to INTENT_CAPTURE, ask for confirmation
        session.state = ConversationState.INTENT_CAPTURE
        agent_text = gemini.INTENT_CONFIRM_TEXT
        audio_out = await gemini.synthesize_speech(agent_text)

    # =========================================================================
    # STATE: INTENT_CAPTURE
    # =========================================================================
    elif session.state == ConversationState.INTENT_CAPTURE:
        if audio_bytes:
            result = await gemini.transcribe_and_extract(
                audio_bytes, "intent", "Does user want to apply for old age pension?", mime_type
            )
            transcript = result["transcript"]
            extracted_value = result["extracted_value"]
            confidence = result["confidence"]
        else:
            extracted_value = transcript

        if sm.process_intent_capture(extracted_value or transcript):
            # User confirmed → start slot filling
            session.state = ConversationState.SLOT_FILLING
            session.current_slot_index = 0
            slot_def = sm.get_current_slot_def(session)
            agent_text = slot_def["tamil_question"] if slot_def else "ஆரம்பிக்கலாம்."
        else:
            agent_text = "சரி, வேறு ஏதாவது உதவி வேண்டுமா?"

        audio_out = await gemini.synthesize_speech(agent_text)

    # =========================================================================
    # STATE: SLOT_FILLING
    # =========================================================================
    elif session.state == ConversationState.SLOT_FILLING:
        current_slot_def = sm.get_current_slot_def(session)
        current_slot_key = sm.get_current_slot_key(session)

        if not current_slot_def or not current_slot_key:
            # All slots done → move to confirmation
            session.state = ConversationState.CONFIRMATION
            session.confirmation_index = 0
            agent_text = gemini.CONFIRMATION_START_TEXT
            audio_out = await gemini.synthesize_speech(agent_text)
        else:
            # Extract from audio
            if audio_bytes:
                result = await gemini.transcribe_and_extract(
                    audio_bytes,
                    current_slot_key,
                    current_slot_def["tamil_question"],
                    mime_type,
                )
                transcript = result["transcript"]
                extracted_value = result["extracted_value"]
                confidence = result["confidence"]
            else:
                extracted_value = transcript

            slot_info = session.slots.get(current_slot_key, SlotInfo())

            # Check for skip offer acceptance
            if slot_info.attempts >= sm.MAX_RETRIES:
                # Was already in skip-offer mode — check if user said yes/no
                lower = (extracted_value or transcript).lower()
                if any(w in lower for w in ["ஆம்", "yes", "சரி", "skip", "தவிர்"]):
                    slot_info.skipped = True
                    slot_info.attempts += 1
                    session.slots[current_slot_key] = slot_info
                    sm.advance_to_next_slot(session)
                    if sm.all_slots_filled(session):
                        session.state = ConversationState.CONFIRMATION
                        session.confirmation_index = 0
                        agent_text = gemini.CONFIRMATION_START_TEXT
                    else:
                        next_def = sm.get_current_slot_def(session)
                        agent_text = next_def["tamil_question"] if next_def else gemini.CONFIRMATION_START_TEXT
                    audio_out = await gemini.synthesize_speech(agent_text)
                else:
                    # Retry once more
                    slot_info.attempts += 1
                    session.slots[current_slot_key] = slot_info
                    agent_text = gemini.build_low_confidence_retry_text(current_slot_def["tamil_question"])
                    audio_out = await gemini.synthesize_speech(agent_text)
            elif confidence == "low" or not sm.validate_slot_value(current_slot_key, extracted_value or ""):
                # Low confidence or validation failure
                slot_info.attempts += 1
                slot_info.confidence = "low"
                session.slots[current_slot_key] = slot_info

                if slot_info.attempts >= sm.MAX_RETRIES:
                    agent_text = gemini.build_skip_offer_text(current_slot_def["tamil_question"])
                else:
                    agent_text = current_slot_def.get(
                        "validator_error_ta",
                        gemini.build_low_confidence_retry_text(current_slot_def["tamil_question"]),
                    )
                audio_out = await gemini.synthesize_speech(agent_text)
            else:
                # High confidence + valid → save and move on
                slot_info.value = extracted_value or transcript
                slot_info.confidence = "high"
                slot_info.attempts += 1
                session.slots[current_slot_key] = slot_info
                sm.advance_to_next_slot(session)

                if sm.all_slots_filled(session):
                    session.state = ConversationState.CONFIRMATION
                    session.confirmation_index = 0
                    agent_text = gemini.CONFIRMATION_START_TEXT
                else:
                    next_def = sm.get_current_slot_def(session)
                    agent_text = next_def["tamil_question"] if next_def else gemini.CONFIRMATION_START_TEXT
                audio_out = await gemini.synthesize_speech(agent_text)

    # =========================================================================
    # STATE: CONFIRMATION
    # =========================================================================
    elif session.state == ConversationState.CONFIRMATION:
        summary = sm.build_confirmation_summary(session)
        idx = session.confirmation_index

        if audio_bytes and idx > 0:
            # User responded to a confirmation question
            result = await gemini.transcribe_and_extract(
                audio_bytes, "confirmation", "Did user confirm yes/no/repeat?", mime_type
            )
            transcript = result["transcript"]
            response_type = sm.process_confirmation_response(result["extracted_value"] or result["transcript"])

            if response_type == "no":
                # Find the slot for this confirmation item and go back to slot filling
                if idx - 1 < len(summary):
                    slot_key_to_fix = summary[idx - 1]["key"]
                    if slot_key_to_fix in session.slots:
                        session.slots[slot_key_to_fix].value = None
                        session.slots[slot_key_to_fix].confidence = None
                        session.slots[slot_key_to_fix].attempts = 0
                    # Find the index of this slot
                    for i, s_def in enumerate(sm.SLOT_DEFINITIONS):
                        if s_def["key"] == slot_key_to_fix:
                            session.current_slot_index = i
                            break
                    session.state = ConversationState.SLOT_FILLING
                    session.retry_count = 0
                    slot_def = sm.get_slot_definition(slot_key_to_fix)
                    agent_text = slot_def.get("tamil_question", "மீண்டும் சொல்லுங்கள்.")
                    audio_out = await gemini.synthesize_speech(agent_text)
                else:
                    agent_text = "மன்னிக்கவும், மீண்டும் ஆரம்பிக்கலாம்."
                    audio_out = await gemini.synthesize_speech(agent_text)

            elif response_type == "repeat" and idx > 0:
                item = summary[idx - 1]
                agent_text = gemini.build_confirmation_item_text(item["label"], item["value"])
                audio_out = await gemini.synthesize_speech(agent_text)
            else:
                # Confirmed — move to next item
                if idx < len(summary):
                    item = summary[idx]
                    agent_text = gemini.build_confirmation_item_text(item["label"], item["value"])
                    session.confirmation_index += 1
                    audio_out = await gemini.synthesize_speech(agent_text)
                else:
                    # All confirmed → submit
                    session.state = ConversationState.SUBMIT
                    agent_text = gemini.CONFIRMATION_ALL_DONE_TEXT
                    audio_out = await gemini.synthesize_speech(agent_text)
        else:
            # First confirmation item
            if summary:
                item = summary[0]
                agent_text = gemini.build_confirmation_item_text(item["label"], item["value"])
                session.confirmation_index = 1
            else:
                agent_text = gemini.CONFIRMATION_ALL_DONE_TEXT
                session.state = ConversationState.SUBMIT
            audio_out = await gemini.synthesize_speech(agent_text)

    # =========================================================================
    # STATE: SUBMIT / DONE
    # =========================================================================
    elif session.state in (ConversationState.SUBMIT, ConversationState.DONE):
        agent_text = "உங்கள் விண்ணப்பம் ஏற்கனவே சமர்ப்பிக்கப்பட்டது. மிக்க நன்றி!"
        audio_out = await gemini.synthesize_speech(agent_text)

    else:
        agent_text = "மன்னிக்கவும், மீண்டும் முயற்சிக்கவும்."
        audio_out = await gemini.synthesize_speech(agent_text)

    # Persist session
    db.update_session(session_id, db.session_to_dict(session))

    return TurnResponse(
        audio_base64=gemini.audio_to_base64(audio_out),
        transcript=transcript,
        agent_text=agent_text,
        state=session.state.value,
        current_slot=sm.get_current_slot_key(session),
        slots={
            k: {
                "value": v.value,
                "confidence": v.confidence,
                "attempts": v.attempts,
                "skipped": v.skipped,
            }
            for k, v in session.slots.items()
        },
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# POST /session/{id}/submit
# ---------------------------------------------------------------------------

@router.post("/{session_id}/submit", response_model=SubmitResponse)
async def submit_session(session_id: str):
    """Finalize the session and write to Supabase."""
    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")

    session = db.dict_to_session_data(session_row)
    form_data = {
        k: v.value for k, v in session.slots.items() if v.value
    }

    ref = db.create_submission(session_id, form_data)
    session.state = ConversationState.DONE
    db.update_session(session_id, db.session_to_dict(session))

    message_text = f"{gemini.SUBMIT_SUCCESS_PREFIX}{ref}{gemini.SUBMIT_SUCCESS_SUFFIX}"
    audio_out = await gemini.synthesize_speech(message_text)

    return SubmitResponse(
        reference_number=ref,
        message=message_text,
        audio_base64=gemini.audio_to_base64(audio_out),
    )


# ---------------------------------------------------------------------------
# GET /session/{id}/debug
# ---------------------------------------------------------------------------

@router.get("/{session_id}/debug", response_model=DebugResponse)
async def debug_session(session_id: str):
    """Return full session state for judges debug panel."""
    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")

    session = db.dict_to_session_data(session_row)
    return DebugResponse(
        session_id=session_id,
        state=session.state.value,
        current_slot=sm.get_current_slot_key(session),
        slots={
            k: {
                "value": v.value,
                "confidence": v.confidence,
                "attempts": v.attempts,
                "skipped": v.skipped,
            }
            for k, v in session.slots.items()
        },
        retry_count=session.retry_count,
        confirmation_index=session.confirmation_index,
    )
