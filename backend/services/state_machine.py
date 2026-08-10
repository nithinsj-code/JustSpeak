"""
State Machine for JustSpeak conversation flow.
States: GREETING → INTENT_CAPTURE → SLOT_FILLING → CONFIRMATION → SUBMIT → DONE
"""

from models.schemas import ConversationState, SessionData, SlotInfo

# Ordered list of slots to collect
SLOT_DEFINITIONS = [
    {
        "key": "full_name",
        "tamil_question": "உங்கள் முழு பெயரை சொல்லுங்கள்.",
        "english_label": "Full Name",
        "validator": lambda v: len(v.strip()) >= 2,
        "validator_error_ta": "பெயர் சரியாக புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "age",
        "tamil_question": "உங்கள் வயது என்ன?",
        "english_label": "Age",
        "validator": lambda v: v.isdigit() and 60 <= int(v) <= 120,
        "validator_error_ta": "பென்ஷன் திட்டத்திற்கு வயது 60 அல்லது அதிகமாக இருக்க வேண்டும். மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "gender",
        "tamil_question": "நீங்கள் ஆண் (male) அல்லது பெண் (female)?",
        "english_label": "Gender",
        "validator": lambda v: v.lower() in ["male", "female", "ஆண்", "பெண்", "man", "woman"],
        "validator_error_ta": "பாலினம் புரியவில்லை. ஆண் அல்லது பெண் என்று சொல்லுங்கள்.",
    },
    {
        "key": "aadhaar_last4",
        "tamil_question": "உங்கள் ஆதார் அட்டையின் கடைசி நான்கு இலக்கங்களை சொல்லுங்கள்.",
        "english_label": "Aadhaar Last 4 Digits",
        "validator": lambda v: len(v.replace(" ", "")) == 4 and v.replace(" ", "").isdigit(),
        "validator_error_ta": "நான்கு இலக்கங்கள் சரியாக புரியவில்லை. மெதுவாக மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "village_district",
        "tamil_question": "நீங்கள் எந்த கிராமம் அல்லது மாவட்டத்தில் வசிக்கிறீர்கள்?",
        "english_label": "Village / District",
        "validator": lambda v: len(v.strip()) >= 2,
        "validator_error_ta": "இடம் புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "has_bank_account",
        "tamil_question": "உங்களுக்கு வங்கி கணக்கு உள்ளதா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
        "english_label": "Has Bank Account",
        "validator": lambda v: v.lower() in ["yes", "no", "ஆம்", "இல்லை", "உள்ளது", "இல்லை"],
        "validator_error_ta": "ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
    },
    {
        "key": "monthly_income_band",
        "tamil_question": "உங்கள் மாத வருமானம் எவ்வளவு? ஆயிரத்திற்கும் குறைவா, ஆயிரம் முதல் இரண்டாயிரம் வரையா, அல்லது இரண்டாயிரத்திற்கும் அதிகமா?",
        "english_label": "Monthly Income Band",
        "validator": lambda v: len(v.strip()) >= 1,
        "validator_error_ta": "வருமானம் புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "phone_number",
        "tamil_question": "உங்கள் தொலைபேசி எண் என்ன? (விரும்பினால் மட்டும் சொல்லுங்கள், வேண்டாம் என்றால் 'தேவையில்லை' என்று சொல்லுங்கள்)",
        "english_label": "Phone Number (Optional)",
        "validator": lambda v: True,  # optional — always accept
        "validator_error_ta": "",
    },
]

MAX_RETRIES = 2


def get_slot_definition(slot_key: str) -> dict:
    for slot in SLOT_DEFINITIONS:
        if slot["key"] == slot_key:
            return slot
    return {}


def get_current_slot_key(session: SessionData) -> str | None:
    idx = session.current_slot_index
    if idx < len(SLOT_DEFINITIONS):
        return SLOT_DEFINITIONS[idx]["key"]
    return None


def get_current_slot_def(session: SessionData) -> dict | None:
    idx = session.current_slot_index
    if idx < len(SLOT_DEFINITIONS):
        return SLOT_DEFINITIONS[idx]
    return None


def validate_slot_value(slot_key: str, value: str) -> bool:
    slot_def = get_slot_definition(slot_key)
    if not slot_def:
        return True
    try:
        return slot_def["validator"](value)
    except Exception:
        return False


def advance_to_next_slot(session: SessionData) -> None:
    """Move to the next unfilled slot."""
    session.current_slot_index += 1
    session.retry_count = 0


def all_slots_filled(session: SessionData) -> bool:
    for slot_def in SLOT_DEFINITIONS:
        key = slot_def["key"]
        slot_info = session.slots.get(key)
        # phone_number is optional, skip if missing
        if key == "phone_number":
            continue
        if not slot_info or (slot_info.value is None and not slot_info.skipped):
            return False
    return True


def build_confirmation_summary(session: SessionData) -> list[dict]:
    """Build a list of {label, value} for confirmation readback."""
    summary = []
    for slot_def in SLOT_DEFINITIONS:
        key = slot_def["key"]
        slot_info = session.slots.get(key)
        if slot_info and slot_info.value:
            summary.append({
                "key": key,
                "label": slot_def["english_label"],
                "value": slot_info.value,
            })
        elif slot_info and slot_info.skipped:
            summary.append({
                "key": key,
                "label": slot_def["english_label"],
                "value": "தவிர்க்கப்பட்டது (skipped)",
            })
    return summary


def process_intent_capture(user_text: str) -> bool:
    """Return True if user confirmed intent to apply for pension."""
    affirm_words = ["ஆம்", "ஆமா", "yes", "சரி", "வேண்டும்", "apply", "ok", "okay", "ha", "haan"]
    lower = user_text.lower()
    return any(w in lower for w in affirm_words)


def process_confirmation_response(user_text: str) -> str:
    """
    Returns 'yes' if user confirmed the field, 'no' if they want to correct it,
    'repeat' if they want it repeated.
    """
    lower = user_text.lower()
    affirm = ["ஆம்", "ஆமா", "yes", "சரி", "correct", "ok", "okay", "right", "ha"]
    deny = ["இல்லை", "no", "தவறு", "wrong", "incorrect", "not right", "மாற்று"]
    repeat = ["மீண்டும்", "repeat", "again", "கேட்க", "படிக்க"]
    if any(w in lower for w in repeat):
        return "repeat"
    if any(w in lower for w in deny):
        return "no"
    if any(w in lower for w in affirm):
        return "yes"
    return "yes"  # default: assume confirmed if unclear
