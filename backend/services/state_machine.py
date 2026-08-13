"""
State Machine for JustSpeak conversation flow.
States: GREETING → INTENT_CAPTURE → SLOT_FILLING → CONFIRMATION → SUBMIT → DONE
"""

from models.schemas import ConversationState, SessionData, SlotInfo

MAX_RETRIES = 3

def get_slot_definition(session: SessionData, slot_key: str) -> dict:
    for slot in session.dynamic_slots:
        if slot["key"] == slot_key:
            return slot
    return {}

def get_slot_question(slot_def: dict, lang: str = "ta") -> str:
    if not slot_def:
        return ""
    return slot_def.get(f"question_{lang}") or slot_def.get("question_en") or ""

def get_slot_label(slot_def: dict, lang: str = "ta") -> str:
    if not slot_def:
        return ""
    return slot_def.get(f"label_{lang}") or slot_def.get("label_en") or ""

def get_slot_error(slot_def: dict, lang: str = "ta") -> str:
    if not slot_def:
        return ""
    return slot_def.get(f"validator_error_{lang}") or slot_def.get("validator_error_en") or (
        "மன்னிக்கவும், புரியவில்லை. மீண்டும் சொல்லுங்கள்." if lang == "ta" else "Sorry, I didn't get that. Please say it again."
    )

def get_current_slot_key(session: SessionData) -> str | None:
    idx = session.current_slot_index
    if idx < len(session.dynamic_slots):
        return session.dynamic_slots[idx]["key"]
    return None

def get_current_slot_def(session: SessionData) -> dict | None:
    idx = session.current_slot_index
    if idx < len(session.dynamic_slots):
        return session.dynamic_slots[idx]
    return None

def validate_slot_value(session: SessionData, slot_key: str, value: str) -> bool:
    # Generic validation for dynamic slots: value must not be empty if not skipped
    return bool(value and str(value).strip())

def advance_to_next_slot(session: SessionData) -> None:
    """Move to the next unfilled slot."""
    session.current_slot_index += 1
    session.retry_count = 0

def all_slots_filled(session: SessionData) -> bool:
    for slot_def in session.dynamic_slots:
        key = slot_def["key"]
        slot_info = session.slots.get(key)
        # Check if optional (can be defined in dynamic_slots)
        is_optional = slot_def.get("optional", False)
        if is_optional:
            continue
        if not slot_info or (slot_info.value is None and not slot_info.skipped):
            return False
    return True

def build_confirmation_summary(session: SessionData) -> list[dict]:
    """Build a list of {label, value} for confirmation readback."""
    summary = []
    lang = getattr(session, "language", "ta") or "ta"
    for slot_def in session.dynamic_slots:
        key = slot_def["key"]
        slot_info = session.slots.get(key)
        label = get_slot_label(slot_def, lang)
        skipped_text = "தவிர்க்கப்பட்டது" if lang == "ta" else "Skipped"
        if slot_info and slot_info.value:
            summary.append({
                "key": key,
                "label": label,
                "value": slot_info.value,
            })
        elif slot_info and slot_info.skipped:
            summary.append({
                "key": key,
                "label": label,
                "value": skipped_text,
            })
    return summary

def process_intent_capture(user_text: str) -> bool:
    """Return True if user confirmed intent to apply for pension.

    Uses whole-word boundary matching so names like 'Noel' or 'Anthony'
    (which contain 'no'/'not' as substrings) are NOT falsely treated as denial.
    """
    import re

    if not user_text or not user_text.strip():
        return True  # default to True if user spoke during greeting/intent

    lower = user_text.strip().lower()

    # If the user just said a short name/phrase (1-3 words, no deny context),
    # treat it as proceeding (they answered the greeting, not denying).
    word_count = len(lower.split())
    if word_count <= 3:
        # Only deny on exact single-word denials like "no", "nope", "stop"
        strict_deny = [
            "no", "nope", "nah", "stop", "cancel",
            "இல்லை", "வேண்டாம்", "வேணாம்", "நிறுத்து", "முடியாது"
        ]
        return lower not in strict_deny

    # For longer responses, use whole-word regex matching to avoid
    # false positives from substrings (e.g., "not" in "Anthony")
    deny_patterns = [
        r"\bno\b", r"\bnot\b", r"\bdon't\b", r"\bdont\b",
        r"\bstop\b", r"\bcancel\b", r"\bnope\b", r"\bnah\b",
        "இல்லை", "வேண்டாம்", "வேணாம்", "நிறுத்து", "முடியாது"
    ]
    for pattern in deny_patterns:
        if re.search(pattern, lower):
            return False
    return True

def process_confirmation_response(user_text: str) -> str:
    """
    Returns 'yes' if user confirmed the field, 'no' if they want to correct it,
    'repeat' if they want it repeated.
    """
    lower = user_text.lower()
    affirm = [
        "yes", "yeah", "correct", "ok", "okay", "right", "sure", "yep", "yup",
        "ஆம்", "சரி", "ஆமா", "ஆமாம்", "கரெக்ட்", "சரிதான்"
    ]
    deny = [
        "no", "wrong", "incorrect", "not right", "change", "fix", "nope",
        "இல்லை", "தவறு", "மாற்று", "வேண்டாம்", "இல்ல"
    ]
    repeat = [
        "repeat", "again", "say again", "one more time", "pardon",
        "மீண்டும்", "திரும்ப", "இன்னொரு முறை", "திரும்ப சொல்லு"
    ]
    if any(w in lower for w in repeat):
        return "repeat"
    if any(w in lower for w in deny):
        return "no"
    if any(w in lower for w in affirm):
        return "yes"
    return "yes"  # default: assume confirmed if unclear
