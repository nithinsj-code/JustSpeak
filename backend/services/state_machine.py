"""
State Machine for JustSpeak conversation flow.
States: GREETING → INTENT_CAPTURE → SLOT_FILLING → CONFIRMATION → SUBMIT → DONE
"""

from models.schemas import ConversationState, SessionData, SlotInfo

# Ordered list of slots to collect
SLOT_DEFINITIONS = [
    {
        "key": "full_name",
        "question": "Please tell me your full name.",
        "english_label": "Full Name",
        "validator": lambda v: len(v.strip()) >= 2,
        "validator_error": "I didn't catch your name. Please say it again.",
    },
    {
        "key": "age",
        "question": "How old are you?",
        "english_label": "Age",
        "validator": lambda v: v.isdigit() and 60 <= int(v) <= 120,
        "validator_error": "You must be 60 years or older for this pension scheme. Please tell me your age again.",
    },
    {
        "key": "gender",
        "question": "Are you male or female?",
        "english_label": "Gender",
        "validator": lambda v: v.lower() in ["male", "female", "man", "woman"],
        "validator_error": "I didn't understand. Please say male or female.",
    },
    {
        "key": "aadhaar_last4",
        "question": "Please tell me the last four digits of your Aadhaar card.",
        "english_label": "Aadhaar Last 4 Digits",
        "validator": lambda v: len(v.replace(" ", "")) == 4 and v.replace(" ", "").isdigit(),
        "validator_error": "I need exactly four digits. Please say them slowly.",
    },
    {
        "key": "village_district",
        "question": "Which village or district do you live in?",
        "english_label": "Village / District",
        "validator": lambda v: len(v.strip()) >= 2,
        "validator_error": "I didn't catch the location. Please say it again.",
    },
    {
        "key": "has_bank_account",
        "question": "Do you have a bank account? Please say yes or no.",
        "english_label": "Has Bank Account",
        "validator": lambda v: v.lower() in ["yes", "no"],
        "validator_error": "Please say yes or no.",
    },
    {
        "key": "monthly_income_band",
        "question": "What is your monthly income? Is it less than a thousand, between one thousand and two thousand, or more than two thousand?",
        "english_label": "Monthly Income Band",
        "validator": lambda v: len(v.strip()) >= 1,
        "validator_error": "I didn't understand your income. Please say it again.",
    },
    {
        "key": "phone_number",
        "question": "What is your phone number? This is optional — say 'skip' if you don't want to provide one.",
        "english_label": "Phone Number (Optional)",
        "validator": lambda v: True,  # optional — always accept
        "validator_error": "",
    },
]

MAX_RETRIES = 4


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
                "value": "Skipped",
            })
    return summary


def process_intent_capture(user_text: str) -> bool:
    """Return True if user confirmed intent to apply for pension."""
    if not user_text or not user_text.strip():
        return True  # default to True if user spoke during greeting/intent
    deny_words = ["no", "don't", "dont", "stop", "cancel", "not", "nope", "nah"]
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
    affirm = ["yes", "yeah", "correct", "ok", "okay", "right", "sure", "yep", "yup"]
    deny = ["no", "wrong", "incorrect", "not right", "change", "fix", "nope"]
    repeat = ["repeat", "again", "say again", "one more time", "pardon"]
    if any(w in lower for w in repeat):
        return "repeat"
    if any(w in lower for w in deny):
        return "no"
    if any(w in lower for w in affirm):
        return "yes"
    return "yes"  # default: assume confirmed if unclear
