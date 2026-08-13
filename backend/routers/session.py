"""
Session router — all conversation endpoints.
"""

import base64
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
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
async def start_session(lang: str = Query("ta", description="Language code: ta or en")):
    """Create a new session and return the greeting audio in selected language."""
    session_id = str(uuid.uuid4())
    language = "en" if lang.lower() == "en" else "ta"

    # Create session in Supabase / mock db
    db.create_session(session_id, language=language)

    # Build greeting audio
    greeting_text = gemini.get_greeting_text(language)
    greeting_audio = await gemini.synthesize_speech(greeting_text, lang=language)
    audio_b64 = gemini.audio_to_base64(greeting_audio)

    return StartSessionResponse(
        session_id=session_id,
        audio_base64=audio_b64,
        state=ConversationState.GREETING.value,
        language=language,
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
        session_row = db.create_session(session_id)

    session = db.dict_to_session_data(session_row)
    lang = getattr(session, "language", "ta") or "ta"

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
    # STATE: GREETING / INTENT_CAPTURE
    # =========================================================================
    if session.state in (ConversationState.GREETING, ConversationState.INTENT_CAPTURE):
        if audio_bytes:
            result = await gemini.transcribe_and_extract(
                audio_bytes, "intent", "Does user want to apply for old age pension?", lang=lang, mime_type=mime_type
            )
            transcript = result.get("transcript", "")
            extracted_value = result.get("value") or result.get("extracted_value", "")
            confidence = result.get("confidence", "low")
        else:
            extracted_value = transcript

        if sm.process_intent_capture(extracted_value or transcript):
            # User confirmed → start slot filling
            session.state = ConversationState.SLOT_FILLING
            session.current_slot_index = 0
            slot_def = sm.get_current_slot_def(session)
            if slot_def:
                q = sm.get_slot_question(slot_def, lang)
                prefix = "சரி. " if lang == "ta" else "Great. "
                agent_text = f"{prefix}{q}"
            else:
                agent_text = "தொடங்கலாம்." if lang == "ta" else "Let's begin."
        else:
            agent_text = (
                "சரி, உதவி தேவைப்படும் போது எப்போது வேண்டுமானாலும் வாருங்கள். நன்றி!"
                if lang == "ta"
                else "Okay, feel free to come back whenever you need help. Thank you!"
            )

        audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

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
            agent_text = gemini.get_confirmation_start_text(lang)
            audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
        else:
            slot_q = sm.get_slot_question(current_slot_def, lang)

            # Extract from audio
            if audio_bytes:
                result = await gemini.transcribe_and_extract(
                    audio_bytes,
                    current_slot_key,
                    slot_q,
                    lang=lang,
                    mime_type=mime_type,
                )
                transcript = result.get("transcript", "")
                extracted_value = result.get("value") or result.get("extracted_value", "")
                confidence = result.get("confidence", "low")
            else:
                extracted_value = transcript

            print(f"[TURN] Slot '{current_slot_key}': transcript='{transcript}', extracted='{extracted_value}', confidence='{confidence}'")
            slot_info = session.slots.get(current_slot_key, SlotInfo())

            # Check for skip offer acceptance
            if slot_info.attempts >= sm.MAX_RETRIES:
                lower = (extracted_value or transcript).lower()
                skip_keywords = ["yes", "yeah", "sure", "ok", "skip", "ஆம்", "சரி", "தவிர்", "ஆமா"]
                if any(w in lower for w in skip_keywords):
                    slot_info.skipped = True
                    slot_info.attempts += 1
                    session.slots[current_slot_key] = slot_info
                    sm.advance_to_next_slot(session)
                    if sm.all_slots_filled(session):
                        session.state = ConversationState.CONFIRMATION
                        session.confirmation_index = 0
                        agent_text = gemini.get_confirmation_start_text(lang)
                    else:
                        next_def = sm.get_current_slot_def(session)
                        agent_text = (
                            sm.get_slot_question(next_def, lang)
                            if next_def
                            else gemini.get_confirmation_start_text(lang)
                        )
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
                else:
                    # Retry once more
                    slot_info.attempts += 1
                    session.slots[current_slot_key] = slot_info
                    agent_text = gemini.build_low_confidence_retry_text(slot_q, lang)
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
            else:
                val_to_use = extracted_value or transcript
                is_valid = sm.validate_slot_value(current_slot_key, val_to_use or "")

                if not val_to_use or not is_valid:
                    # Empty or validation failure
                    slot_info.attempts += 1
                    slot_info.confidence = "low"
                    session.slots[current_slot_key] = slot_info

                    if slot_info.attempts >= sm.MAX_RETRIES:
                        agent_text = gemini.build_skip_offer_text(slot_q, lang)
                    else:
                        err_msg = sm.get_slot_error(current_slot_def, lang)
                        agent_text = err_msg or gemini.build_low_confidence_retry_text(slot_q, lang)
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
                else:
                    # Valid value → save and move on
                    slot_info.value = val_to_use
                    slot_info.confidence = confidence or "high"
                    slot_info.attempts += 1
                    session.slots[current_slot_key] = slot_info
                    sm.advance_to_next_slot(session)

                    if sm.all_slots_filled(session):
                        session.state = ConversationState.CONFIRMATION
                        session.confirmation_index = 0
                        agent_text = gemini.get_confirmation_start_text(lang)
                    else:
                        next_def = sm.get_current_slot_def(session)
                        agent_text = (
                            sm.get_slot_question(next_def, lang)
                            if next_def
                            else gemini.get_confirmation_start_text(lang)
                        )
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

    # =========================================================================
    # STATE: CONFIRMATION
    # =========================================================================
    elif session.state == ConversationState.CONFIRMATION:
        summary = sm.build_confirmation_summary(session)
        idx = session.confirmation_index

        if audio_bytes and idx > 0:
            result = await gemini.transcribe_and_extract(
                audio_bytes, "confirmation", "Did user confirm yes/no/repeat?", lang=lang, mime_type=mime_type
            )
            transcript = result.get("transcript", "")
            val = result.get("value") or result.get("extracted_value") or transcript
            response_type = sm.process_confirmation_response(val)

            if response_type == "no":
                if idx - 1 < len(summary):
                    slot_key_to_fix = summary[idx - 1]["key"]
                    if slot_key_to_fix in session.slots:
                        session.slots[slot_key_to_fix].value = None
                        session.slots[slot_key_to_fix].confidence = None
                        session.slots[slot_key_to_fix].attempts = 0
                    for i, s_def in enumerate(sm.SLOT_DEFINITIONS):
                        if s_def["key"] == slot_key_to_fix:
                            session.current_slot_index = i
                            break
                    session.state = ConversationState.SLOT_FILLING
                    session.retry_count = 0
                    slot_def = sm.get_slot_definition(slot_key_to_fix)
                    agent_text = sm.get_slot_question(slot_def, lang) or "மீண்டும் சொல்லுங்கள்."
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
                else:
                    agent_text = "மன்னிக்கவும், மீண்டும் தொடங்கலாம்." if lang == "ta" else "Sorry, let's start again."
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

            elif response_type == "repeat" and idx > 0:
                item = summary[idx - 1]
                agent_text = gemini.build_confirmation_item_text(item["label"], item["value"], lang)
                audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
            else:
                # Confirmed → next item
                if idx < len(summary):
                    item = summary[idx]
                    agent_text = gemini.build_confirmation_item_text(item["label"], item["value"], lang)
                    session.confirmation_index += 1
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
                else:
                    # All confirmed → submit
                    session.state = ConversationState.SUBMIT
                    agent_text = gemini.get_confirmation_all_done_text(lang)
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
        else:
            # First confirmation item
            if summary:
                item = summary[0]
                agent_text = gemini.build_confirmation_item_text(item["label"], item["value"], lang)
                session.confirmation_index = 1
            else:
                agent_text = gemini.get_confirmation_all_done_text(lang)
                session.state = ConversationState.SUBMIT
            audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

    # =========================================================================
    # STATE: SUBMIT / DONE
    # =========================================================================
    elif session.state in (ConversationState.SUBMIT, ConversationState.DONE):
        agent_text = (
            "உங்கள் விண்ணப்பம் ஏற்கனவே சமர்ப்பிக்கப்பட்டது. நன்றி!"
            if lang == "ta"
            else "Your application has already been submitted. Thank you!"
        )
        audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

    else:
        agent_text = "மன்னிக்கவும், மீண்டும் முயற்சிக்கவும்." if lang == "ta" else "Sorry, please try again."
        audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

    # Persist session
    db.update_session(session_id, db.session_to_dict(session))

    return TurnResponse(
        audio_base64=gemini.audio_to_base64(audio_out),
        transcript=transcript,
        agent_text=agent_text,
        state=session.state.value,
        language=lang,
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
    lang = getattr(session, "language", "ta") or "ta"
    form_data = {
        k: v.value for k, v in session.slots.items() if v.value
    }

    ref = db.create_submission(session_id, form_data)
    session.state = ConversationState.DONE
    db.update_session(session_id, db.session_to_dict(session))

    message_text = gemini.get_submit_success_text(ref, lang=lang)
    audio_out = await gemini.synthesize_speech(message_text, lang=lang)

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
        language=getattr(session, "language", "ta") or "ta",
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
