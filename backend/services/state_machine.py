"""
State Machine for JustSpeak conversation flow.
States: GREETING → INTENT_CAPTURE → SLOT_FILLING → CONFIRMATION → SUBMIT → DONE
"""

from models.schemas import ConversationState, SessionData, SlotInfo

# Ordered list of slots to collect with bilingual support
SLOT_DEFINITIONS = [
    {
        "key": "full_name",
        "question_en": "Please tell me your full name.",
        "question_ta": "உங்கள் முழு பெயரைச் சொல்லுங்கள்.",
        "label_en": "Full Name",
        "label_ta": "முழு பெயர்",
        "validator": lambda v: len(v.strip()) >= 2,
        "validator_error_en": "I didn't catch your name. Please say it again.",
        "validator_error_ta": "உங்கள் பெயர் எனக்குப் புரியவில்லை. உங்கள் பெயரை மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "age",
        "question_en": "How old are you?",
        "question_ta": "உங்கள் வயது என்ன?",
        "label_en": "Age",
        "label_ta": "வயது",
        "validator": lambda v: v.isdigit() and 60 <= int(v) <= 120,
        "validator_error_en": "You must be 60 years or older for this pension scheme. Please tell me your age again.",
        "validator_error_ta": "இந்த முதியோர் உதவித்தொகை திட்டத்திற்கு 60 வயது அல்லது அதற்கு மேல் இருக்க வேண்டும். உங்கள் வயதை மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "gender",
        "question_en": "Are you male or female?",
        "question_ta": "நீங்கள் ஆணா அல்லது பெண்ணா?",
        "label_en": "Gender",
        "label_ta": "பாலினம்",
        "validator": lambda v: any(w in v.lower() for w in ["male", "female", "man", "woman", "ஆண்", "பெண்"]),
        "validator_error_en": "I didn't understand. Please say male or female.",
        "validator_error_ta": "புரியவில்லை. ஆண் அல்லது பெண் என்று சொல்லுங்கள்.",
    },
    {
        "key": "aadhaar_last4",
        "question_en": "Please tell me the last four digits of your Aadhaar card.",
        "question_ta": "உங்கள் ஆதார் அட்டையின் கடைசி நான்கு எண்களைச் சொல்லுங்கள்.",
        "label_en": "Aadhaar Last 4 Digits",
        "label_ta": "ஆதார் கடைசி 4 எண்கள்",
        "validator": lambda v: len(v.replace(" ", "")) == 4 and v.replace(" ", "").isdigit(),
        "validator_error_en": "I need exactly four digits. Please say them slowly.",
        "validator_error_ta": "சரியாக நான்கு எண்களை மெதுவாக சொல்லுங்கள்.",
    },
    {
        "key": "village_district",
        "question_en": "Which village or district do you live in?",
        "question_ta": "நீங்கள் எந்த ஊர் அல்லது மாவட்டத்தில் வசிக்கிறீர்கள்?",
        "label_en": "Village / District",
        "label_ta": "ஊர் / மாவட்டம்",
        "validator": lambda v: len(v.strip()) >= 2,
        "validator_error_en": "I didn't catch the location. Please say it again.",
        "validator_error_ta": "ஊரின் பெயர் புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "has_bank_account",
        "question_en": "Do you have a bank account? Please say yes or no.",
        "question_ta": "உங்களுக்கு வங்கி கணக்கு உள்ளதா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
        "label_en": "Has Bank Account",
        "label_ta": "வங்கி கணக்கு",
        "validator": lambda v: any(w in v.lower() for w in ["yes", "no", "ஆம்", "இல்லை", "ஆமா", "இல்ல"]),
        "validator_error_en": "Please say yes or no.",
        "validator_error_ta": "ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
    },
    {
        "key": "monthly_income_band",
        "question_en": "What is your monthly income? Is it less than a thousand, between one thousand and two thousand, or more than two thousand?",
        "question_ta": "உங்கள் மாத வருமானம் எவ்வளவு? ஆயிரத்திற்கும் குறைவா, ஆயிரத்திலிருந்து இரண்டாயிரமா, அல்லது இரண்டாயிரத்திற்கு மேல் உள்ளதா?",
        "label_en": "Monthly Income",
        "label_ta": "மாத வருமானம்",
        "validator": lambda v: len(v.strip()) >= 1,
        "validator_error_en": "I didn't understand your income. Please say it again.",
        "validator_error_ta": "உங்கள் வருமானம் புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    },
    {
        "key": "phone_number",
        "question_en": "What is your phone number? This is optional — say 'skip' if you don't want to provide one.",
        "question_ta": "உங்கள் தொலைபேசி எண் என்ன? இது கட்டாயமில்லை — விருப்பமில்லை என்றால் 'தவிர்' என்று சொல்லலாம்.",
        "label_en": "Phone Number (Optional)",
        "label_ta": "தொலைபேசி எண்",
        "validator": lambda v: True,  # optional — always accept
        "validator_error_en": "",
        "validator_error_ta": "",
    },
]

MAX_RETRIES = 3


def get_slot_definition(slot_key: str) -> dict:
    for slot in SLOT_DEFINITIONS:
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
    return slot_def.get(f"validator_error_{lang}") or slot_def.get("validator_error_en") or ""


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
    lang = getattr(session, "language", "ta") or "ta"
    for slot_def in SLOT_DEFINITIONS:
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
    """Return True if user confirmed intent to apply for pension."""
    if not user_text or not user_text.strip():
        return True  # default to True if user spoke during greeting/intent
    deny_words = [
        "no", "don't", "dont", "stop", "cancel", "not", "nope", "nah",
        "இல்லை", "வேண்டாம்", "வேணாம்", "நிறுத்து", "முடியாது"
    ]
    lower = user_text.lower()
    if any(w in lower for w in deny_words):
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
