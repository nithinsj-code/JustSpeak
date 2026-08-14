"""
Vision Service — Uses Playwright to screenshot a government form URL
and Gemini Vision to dynamically extract the slot definitions.
"""

import base64
import json
import re

from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------

async def capture_form_screenshot(url: str) -> bytes:
    """Open a browser, navigate to the URL, take a full-page screenshot and return PNG bytes."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Scroll to load lazy elements
            await page.evaluate("window.scrollTo(0, 0)")
            screenshot_bytes = await page.screenshot(full_page=True)
            return screenshot_bytes
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Vision-based slot extraction using Gemini
# ---------------------------------------------------------------------------

VISION_EXTRACTION_PROMPT = """
You are an expert at analyzing government form screenshots and extracting what information needs to be collected from the user.

I will provide you with a screenshot of a government form web page.

Your task is to extract ALL the form fields visible on the page and return a JSON array of slot definitions.

Each slot definition must have:
{
  "key": "<snake_case_field_name>",
  "label_en": "<Field label in English>",
  "label_ta": "<Field label in Tamil if possible, else same as English>",
  "question_en": "<Natural question to ask the user in English, e.g. 'What is your full name?'>",
  "question_ta": "<Natural question in Tamil, e.g. 'உங்கள் முழு பெயர் என்ன?'>",
  "input_type": "<text|number|select|radio|checkbox>",
  "options": ["<option1>", "<option2>"] or null if not a select/radio,
  "optional": false
}

Rules:
- Only include visible form fields. Skip buttons, headings, and non-input elements.
- Generate a unique snake_case key for each field.
- Write natural, conversational questions as if a human assistant is speaking to an elderly person.
- For Tamil questions, write in simple Tamil script.
- If a field appears optional (e.g., has "(Optional)" in its label), set "optional": true.
- For select/radio fields, populate the "options" array with the visible choices.
- Return ONLY a valid JSON array. No markdown, no code fences, no explanation.
"""


async def extract_slots_from_screenshot(screenshot_bytes: bytes, gemini_client, models: list) -> list[dict]:
    """Send screenshot to Gemini Vision and get a list of slot definitions back."""
    from google.genai import types

    img_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    image_part = types.Part.from_bytes(data=screenshot_bytes, mime_type="image/png")

    last_err = None
    for model_name in models:
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=[VISION_EXTRACTION_PROMPT, image_part],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            raw = response.text.strip()
            # Strip code fences if present
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
            slots = json.loads(raw)
            if isinstance(slots, list) and len(slots) > 0:
                print(f"[VISION] Extracted {len(slots)} slots from screenshot using model {model_name}")
                return slots
        except Exception as e:
            last_err = e
            print(f"[VISION] Model '{model_name}' failed ({type(e).__name__}: {e}). Trying next...")
            continue

    print(f"[VISION] All models failed. Last error: {last_err}. Using fallback slots.")
    return _fallback_slots()


def _fallback_slots() -> list[dict]:
    """Returns basic fallback slots if vision parsing fails."""
    return [
        {
            "key": "full_name",
            "label_en": "Full Name",
            "label_ta": "முழு பெயர்",
            "question_en": "What is your full name?",
            "question_ta": "உங்கள் முழு பெயர் என்ன?",
            "input_type": "text",
            "options": None,
            "optional": False,
        },
        {
            "key": "age",
            "label_en": "Age",
            "label_ta": "வயது",
            "question_en": "How old are you?",
            "question_ta": "உங்கள் வயது என்ன?",
            "input_type": "number",
            "options": None,
            "optional": False,
        },
        {
            "key": "gender",
            "label_en": "Gender",
            "label_ta": "பாலினம்",
            "question_en": "What is your gender — male or female?",
            "question_ta": "நீங்கள் ஆண் அல்லது பெண்?",
            "input_type": "select",
            "options": ["Male", "Female", "Other"],
            "optional": False,
        },
        {
            "key": "aadhaar_last4",
            "label_en": "Aadhaar Last 4 Digits",
            "label_ta": "ஆதார் கடைசி 4 இலக்கங்கள்",
            "question_en": "What are the last 4 digits of your Aadhaar card?",
            "question_ta": "உங்கள் ஆதார் கார்டின் கடைசி 4 இலக்கங்கள் என்ன?",
            "input_type": "text",
            "options": None,
            "optional": False,
        },
        {
            "key": "village_district",
            "label_en": "Village / District",
            "label_ta": "கிராமம் / மாவட்டம்",
            "question_en": "Which village or district do you live in?",
            "question_ta": "நீங்கள் எந்த கிராமம் அல்லது மாவட்டத்தில் வசிக்கிறீர்கள்?",
            "input_type": "text",
            "options": None,
            "optional": False,
        },
        {
            "key": "has_bank_account",
            "label_en": "Bank Account",
            "label_ta": "வங்கி கணக்கு",
            "question_en": "Do you have a bank account? Please say yes or no.",
            "question_ta": "உங்களுக்கு வங்கி கணக்கு இருக்கிறதா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்.",
            "input_type": "select",
            "options": ["Yes", "No"],
            "optional": False,
        },
        {
            "key": "monthly_income_band",
            "label_en": "Monthly Income",
            "label_ta": "மாத வருமானம்",
            "question_en": "What is your monthly income? Is it less than 1000, between 1000 and 2000, or more than 2000?",
            "question_ta": "உங்கள் மாத வருமானம் என்ன? ஆயிரத்திற்கும் குறைவா, ஆயிரத்திலிருந்து இரண்டாயிரம் வரையா, அல்லது இரண்டாயிரத்திற்கும் அதிகமா?",
            "input_type": "select",
            "options": ["Less than 1000", "1000 to 2000", "More than 2000"],
            "optional": False,
        },
    ]
