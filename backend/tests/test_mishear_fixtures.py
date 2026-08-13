"""
Mishear Recovery Test Fixtures
Tests 8 realistic Tamil utterances through the STT+LLM pipeline.

Run: python tests/test_mishear_fixtures.py
(Requires GEMINI_API_KEY in .env and internet connection)
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

# We'll test with text input (simulating what Gemini STT would produce)
# In real tests, replace TEXT_FIXTURES with actual audio files

TEXT_FIXTURES = [
    # (slot_key, utterance, expected_confidence, expected_value_approx)
    {
        "id": 1,
        "description": "Clear name — clean input",
        "slot_key": "full_name",
        "transcript": "என் பெயர் முத்துலட்சுமி",
        "expected_confidence": "high",
        "expected_value_contains": "முத்துலட்சுமி",
    },
    {
        "id": 2,
        "description": "Mumbled/ambiguous age — 66 or 70",
        "slot_key": "age",
        "transcript": "அறுபத்தி... அறு... எழுபது",
        "expected_confidence": "low",
        "expected_value_contains": None,
    },
    {
        "id": 3,
        "description": "Accented village name",
        "slot_key": "village_district",
        "transcript": "திருவண்ணாமலை மாவட்டம்",
        "expected_confidence": "high",
        "expected_value_contains": "திருவண்ணாமலை",
    },
    {
        "id": 4,
        "description": "Aadhaar digits with pauses",
        "slot_key": "aadhaar_last4",
        "transcript": "கடைசி நான்கு... ஐந்து ஆறு... ஏழு... எட்டு",
        "expected_confidence": "high",
        "expected_value_contains": "5678",
    },
    {
        "id": 5,
        "description": "Out-of-range age (too young for pension)",
        "slot_key": "age",
        "transcript": "முப்பத்தைந்து",
        "expected_confidence": "low",  # 35 fails validation
        "expected_value_contains": None,
    },
    {
        "id": 6,
        "description": "Clear gender — female",
        "slot_key": "gender",
        "transcript": "நான் பெண்",
        "expected_confidence": "high",
        "expected_value_contains": "female",
    },
    {
        "id": 7,
        "description": "Phone number with pauses",
        "slot_key": "phone_number",
        "transcript": "ஒன்பது ஒன்பது... எட்டு ஏழு... ஆறு ஐந்து... நான்கு மூன்று இரண்டு ஒன்று",
        "expected_confidence": "high",
        "expected_value_contains": None,  # just check it doesn't crash
    },
    {
        "id": 8,
        "description": "Income band — below 1000",
        "slot_key": "monthly_income_band",
        "transcript": "ஆயிரத்திற்கும் குறைவாக இருக்கிறது",
        "expected_confidence": "high",
        "expected_value_contains": None,
    },
]


async def run_text_fixture_test(fixture: dict) -> dict:
    """
    Simulate STT by sending the transcript text directly to the LLM extraction.
    In real usage, audio bytes would be sent.
    """
    from google import genai
    from google.genai import types

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=GEMINI_API_KEY)

    system_prompt = f"""You are a Tamil speech recognition and form data extraction assistant.
The user's spoken transcription is provided. Extract the value for the field.

Return ONLY a valid JSON object:
{{
  "transcript": "<the input text>",
  "extracted_value": "<clean extracted value>",
  "confidence": "high" or "low",
  "reasoning": "<brief explanation>"
}}

Rules:
- For age: extract only the number. If ambiguous or below 60, set confidence=low.
- For aadhaar_last4: extract exactly 4 digits.
- For gender: normalize to "male" or "female".
- For phone_number: extract digits.
- confidence = "low" if ambiguous, unclear, or fails expected range.

Current field: {fixture['slot_key']}
"""

    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=[system_prompt, f"User said: {fixture['transcript']}"],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    result = json.loads(response.text)
    return result


async def run_all_fixtures():
    print("=" * 60)
    print("JustSpeak — Mishear Recovery Test Fixtures")
    print("=" * 60)

    passed = 0
    failed = 0

    for fixture in TEXT_FIXTURES:
        print(f"\n[{fixture['id']}] {fixture['description']}")
        print(f"    Slot: {fixture['slot_key']}")
        print(f"    Input: {fixture['transcript']}")

        try:
            result = await run_text_fixture_test(fixture)
            got_confidence = result.get("confidence", "?")
            got_value = result.get("extracted_value", "?")
            reasoning = result.get("reasoning", "")

            print(f"    → Confidence: {got_confidence} (expected: {fixture['expected_confidence']})")
            print(f"    → Value: {got_value}")
            print(f"    → Reasoning: {reasoning}")

            # Check confidence match
            confidence_ok = got_confidence == fixture["expected_confidence"]

            # Check value contains expected substring
            value_ok = True
            if fixture["expected_value_contains"]:
                value_ok = fixture["expected_value_contains"].lower() in str(got_value).lower()

            if confidence_ok and value_ok:
                print(f"    ✅ PASS")
                passed += 1
            else:
                issues = []
                if not confidence_ok:
                    issues.append(f"confidence mismatch (got {got_confidence})")
                if not value_ok:
                    issues.append(f"value missing '{fixture['expected_value_contains']}'")
                print(f"    ❌ FAIL — {', '.join(issues)}")
                failed += 1

        except Exception as e:
            print(f"    ❌ ERROR — {e}")
            failed += 1

        # Rate limit protection (free tier is 5 RPM)
        await asyncio.sleep(4)

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(TEXT_FIXTURES)} fixtures")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_fixtures())
