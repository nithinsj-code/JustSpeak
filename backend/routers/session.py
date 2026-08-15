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
from services import browser_automation
from services import vision_service

router = APIRouter(prefix="/session", tags=["session"])


# Default target URL — the mock gov site we created.
# In real deployment, this would be the actual government pension form URL.
DEFAULT_FORM_URL = "http://localhost:8000/static/mock_gov_site.html"


# ---------------------------------------------------------------------------
# POST /session/start
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StartSessionResponse)
async def start_session(
    lang: str = Query("ta", description="Language code: ta or en"),
    target_url: str = Query(None, description="Optional URL of the government form to fill"),
):
    """
    Create a new session. Uses Gemini Vision to parse the target form URL
    and generate dynamic slot definitions, then returns the greeting audio.
    """
    session_id = str(uuid.uuid4())
    language = "en" if lang.lower() == "en" else "ta"

    # --- Step 1: Vision-Based Dynamic Slot Extraction ---
    form_url = target_url or DEFAULT_FORM_URL
    print(f"[SESSION] Starting vision-based slot extraction from: {form_url}")

    try:
        screenshot_bytes = await vision_service.capture_form_screenshot(form_url)
        dynamic_slots = await vision_service.extract_slots_from_screenshot(
            screenshot_bytes,
            gemini.client,
            gemini.PRIMARY_MODELS,
        )
    except Exception as e:
        print(f"[SESSION] Vision extraction failed: {e}. Using fallback slots.")
        dynamic_slots = vision_service._fallback_slots()

    # --- Step 2: Create session in DB ---
    db.create_session(session_id, language=language)

    # --- Step 3: Persist dynamic_slots in session ---
    session_row = db.get_session(session_id)
    session = db.dict_to_session_data(session_row)
    session.dynamic_slots = dynamic_slots
    db.update_session(session_id, db.session_to_dict(session))

    # --- Step 4: Build greeting audio ---
    greeting_text = gemini.get_greeting_text(language)
    greeting_audio = await gemini.synthesize_speech(greeting_text, lang=language)
    audio_b64 = gemini.audio_to_base64(greeting_audio)

    # --- Step 5: Return slots_config to frontend ---
    slots_config = [
        {
            "key": s["key"],
            "label_en": s.get("label_en", s["key"]),
            "label_ta": s.get("label_ta", s["key"]),
        }
        for s in dynamic_slots
    ]

    return StartSessionResponse(
        session_id=session_id,
        audio_base64=audio_b64,
        state=ConversationState.GREETING.value,
        language=language,
        slots_config=slots_config,
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

    # If dynamic_slots is empty (old session), load fallback
    if not session.dynamic_slots:
        session.dynamic_slots = vision_service._fallback_slots()

    transcript = ""
    extracted_value = ""
    confidence = "high"
    audio_bytes = None
    mime_type = "audio/webm"
    result = {}


    # --- Read audio or text ---
    if audio:
        audio_bytes = await audio.read()
        mime_type = audio.content_type or "audio/webm"
    elif text_input:
        transcript = text_input
    else:
        raise HTTPException(status_code=400, detail="Provide either audio or text_input")

    # =========================================================================
    # STATE: GREETING / INTENT_CAPTURE
    # =========================================================================
    if session.state in (ConversationState.GREETING, ConversationState.INTENT_CAPTURE):
        if audio_bytes:
            result = await gemini.transcribe_and_extract(
                audio_bytes, "intent", "Does user want to apply for the government pension form?",
                lang=lang, mime_type=mime_type,
            )
            transcript = result.get("transcript", "")
            extracted_value = result.get("value") or ""
            confidence = result.get("confidence", "low")
        else:
            extracted_value = transcript

        # Use the raw transcript for intent detection — NOT extracted_value.
        # extracted_value for an "intent" slot can accidentally capture a name
        # or unrelated phrase (e.g. user says their name instead of "yes"),
        # which may contain deny-word substrings and trigger a false rejection.
        # The transcript is the verbatim speech, which is safer to check.
        # Also: if confidence is low, the user spoke something unclear — treat
        # it as intent to proceed (they are engaging, not refusing).
        intent_text = transcript or extracted_value
        intent_confirmed = (
            sm.process_intent_capture(intent_text)
            if intent_text.strip()
            else True  # empty audio → proceed by default
        )

        # Additional safety: if confidence is "low" and no explicit denial
        # in the raw transcript, always proceed (user is engaging with the app)
        if not intent_confirmed and confidence == "low":
            print(f"[INTENT] Low-confidence response, defaulting to proceed. transcript='{transcript}'")
            intent_confirmed = True

        if intent_confirmed:
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
            agent_text = (
                "படிவம் முழுமையாக நிரப்பப்பட்டுள்ளது. திரையில் உள்ள விவரங்களைச் சரிபார்க்கவும். எல்லாம் சரியாக உள்ளதா?"
                if lang == "ta"
                else "The form is fully filled. Please check the details on the screen. Is everything correct?"
            )
            audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
        else:
            slot_q = sm.get_slot_question(current_slot_def, lang)
            target_field = current_slot_key  # default

            # --- Extract from audio ---
            if audio_bytes:
                result = await gemini.transcribe_and_extract(
                    audio_bytes,
                    current_slot_key,
                    slot_q,
                    lang=lang,
                    mime_type=mime_type,
                )
                transcript = result.get("transcript", "")
                extracted_value = result.get("value") or ""
                target_field = result.get("target_field") or current_slot_key
                confidence = result.get("confidence", "low")
            else:
                extracted_value = transcript

            print(f"[TURN] Slot '{current_slot_key}': transcript='{transcript}', "
                  f"extracted='{extracted_value}', target_field='{target_field}', confidence='{confidence}'")

            # ==================================================================
            # MID-FLOW CORRECTION: User is explicitly correcting a PREVIOUS field
            # ==================================================================
            correction_keywords = [
                "மாற்று", "மாத்து", "தவறு", "தப்பாக", "இல்லை என்", "மாத்தணும்",
                "wait", "change", "correct", "wrong", "mistake", "update my", "edit my"
            ]
            has_correction_intent = any(w in transcript.lower() for w in correction_keywords)
            is_correction = (
                has_correction_intent
                and target_field != current_slot_key
                and any(s["key"] == target_field for s in session.dynamic_slots)
            )

            # Check if STT failed due to an API Rate Limit/Overload
            api_error = result.get("error") == "api_error" if audio_bytes else False

            if api_error:
                agent_text = (
                    "மன்னிக்கவும், சர்வர் மிகவும் பிஸியாக உள்ளது. சிறிது நேரம் கழித்து மீண்டும் சொல்லுங்கள்."
                    if lang == "ta"
                    else "Sorry, the system is currently overloaded. Please wait a moment and try again."
                )
                audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
            elif is_correction:
                if extracted_value and target_field != "intent":
                    # Update the targeted slot
                    corrected_slot = session.slots.get(target_field, SlotInfo())
                    corrected_slot.value = extracted_value
                    corrected_slot.confidence = "high"
                    session.slots[target_field] = corrected_slot

                    # Build acknowledgement
                    target_def = sm.get_slot_definition(session, target_field)
                    label = sm.get_slot_label(target_def, lang)
                    if lang == "ta":
                        ack = f"சரி, {label} '{extracted_value}' என்று மாற்றினேன். "
                    else:
                        ack = f"Okay, I've updated your {label} to '{extracted_value}'. "

                    # Resume asking current question
                    agent_text = ack + slot_q
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
                else:
                    # Unclear correction attempt — retry current slot
                    agent_text = (
                        f"மன்னிக்கவும், புரியவில்லை. {slot_q}"
                        if lang == "ta"
                        else f"Sorry, I didn't catch that. {slot_q}"
                    )
                    audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

            # ==================================================================
            # NORMAL SLOT FILLING
            # ==================================================================
            else:
                slot_info = session.slots.get(current_slot_key, SlotInfo())

                # Treat literal "null" string (from older Gemini prompt) as empty
                clean_extracted = extracted_value if extracted_value not in ("", "null", "None") else ""
                val_to_use = clean_extracted or transcript.strip()
                lower = (val_to_use).lower()

                # Check for skip offer acceptance (after MAX retries)
                if slot_info.attempts >= sm.MAX_RETRIES:
                    skip_keywords = ["yes", "yeah", "sure", "ok", "skip", "ஆம்", "சரி", "தவிர்", "ஆமா"]
                    if any(w in lower for w in skip_keywords):
                        # Mark as skipped and move on
                        slot_info.skipped = True
                        slot_info.attempts += 1
                        session.slots[current_slot_key] = slot_info
                        sm.advance_to_next_slot(session)
                        if sm.all_slots_filled(session):
                            session.state = ConversationState.CONFIRMATION
                            agent_text = (
                                "படிவம் முழுமையாக நிரப்பப்பட்டுள்ளது. திரையில் உள்ள விவரங்களைச் சரிபார்க்கவும். எல்லாம் சரியாக உள்ளதா?"
                                if lang == "ta"
                                else "The form is fully filled. Please check the details on the screen. Is everything correct?"
                            )
                        else:
                            next_def = sm.get_current_slot_def(session)
                            agent_text = (
                                sm.get_slot_question(next_def, lang)
                                if next_def
                                else gemini.get_confirmation_start_text(lang)
                            )
                        audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
                    else:
                        slot_info.attempts += 1
                        session.slots[current_slot_key] = slot_info
                        agent_text = gemini.build_low_confidence_retry_text(slot_q, lang)
                        audio_out = await gemini.synthesize_speech(agent_text, lang=lang)

                else:
                    is_valid = sm.validate_slot_value(session, current_slot_key, val_to_use or "")

                    if not val_to_use or not is_valid:
                        # Empty or unclear — ask again, DON'T save mock data
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
                            agent_text = (
                                "படிவம் முழுமையாக நிரப்பப்பட்டுள்ளது. திரையில் உள்ள விவரங்களைச் சரிபார்க்கவும். எல்லாம் சரியாக உள்ளதா?"
                                if lang == "ta"
                                else "The form is fully filled. Please check the details on the screen. Is everything correct?"
                            )
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
        if audio_bytes:
            result = await gemini.transcribe_and_extract(
                audio_bytes, "confirmation", "Did user confirm yes or no?", lang=lang, mime_type=mime_type
            )
            transcript = result.get("transcript", "")
            val = result.get("value") or result.get("extracted_value") or transcript
            response_type = sm.process_confirmation_response(val)

            if response_type == "no":
                # Restart slot filling from scratch
                session.state = ConversationState.SLOT_FILLING
                session.current_slot_index = 0
                for k in session.slots:
                    session.slots[k].value = None
                    session.slots[k].confidence = None
                    session.slots[k].attempts = 0

                next_def = sm.get_current_slot_def(session)
                q = sm.get_slot_question(next_def, lang)
                agent_text = (
                    f"சரி, மீண்டும் தொடங்குவோம். {q}"
                    if lang == "ta"
                    else f"Okay, let's start over. {q}"
                )
                audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
            else:
                # Confirmed → trigger submit
                session.state = ConversationState.SUBMIT
                agent_text = gemini.get_confirmation_all_done_text(lang)
                audio_out = await gemini.synthesize_speech(agent_text, lang=lang)
        else:
            # First request: prompt visual check
            agent_text = (
                "படிவம் முழுமையாக நிரப்பப்பட்டுள்ளது. திரையில் உள்ள விவரங்களைச் சரிபார்க்கவும். எல்லாம் சரியாக உள்ளதா?"
                if lang == "ta"
                else "The form is fully filled. Please check the details on the screen. Is everything correct?"
            )
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
    """Finalize session — trigger Playwright automation and return reference number."""
    session_row = db.get_session(session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")

    session = db.dict_to_session_data(session_row)
    lang = getattr(session, "language", "ta") or "ta"
    form_data = {k: v.value for k, v in session.slots.items() if v.value}

    # Delegate to Playwright automation
    ref = await browser_automation.submit_pension_application(form_data)

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
