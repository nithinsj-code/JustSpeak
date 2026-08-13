"""
Gemini Service — STT, LLM dialogue, and TTS using the new google-genai SDK.
Uses a single GEMINI_API_KEY for everything.
"""

import base64
import json
import os
import re
import struct
from io import BytesIO

from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from gtts import gTTS  # type: ignore # pyrefly: ignore [missing-import]
except ImportError:
    gTTS = None

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MOCK_MODE = not GEMINI_API_KEY or "your_gemini_api_key" in GEMINI_API_KEY

if MOCK_MODE:
    print("[GEMINI] Running in MOCK MODE (using stub responses)")
    client = None
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

# Model IDs
STT_LLM_MODEL  = "gemini-2.0-flash"
TTS_MODEL      = "gemini-2.5-flash-preview-tts"
DIALOGUE_MODEL = "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# STT + Slot Extraction (single call: audio → JSON)
# ---------------------------------------------------------------------------

STT_EXTRACT_SYSTEM = """You are an English speech recognition and form data extraction assistant.
The user is applying for the Old Age Pension Scheme via a voice-first application.

You will receive an audio clip of the user's spoken response and context about what field is being collected.

Return ONLY a valid JSON object (no markdown, no code fences) with these exact fields:
{{
  "transcript": "<verbatim English transcription of what was said>",
  "value": "<the clean extracted value for the field, normalized>",
  "confidence": "high or low"
}}

Rules:
- confidence = "high" if you clearly understood the spoken value and it fits the expected field
- confidence = "low" if audio was unclear, ambiguous, noisy, or value does not make sense for the field
- For intent: if user says "yes", "yeah", "sure", "ok", "apply", "I want to apply", or expresses willingness, set value = "yes" and confidence = "high".
- For full_name: extract the spoken person name (e.g., "My name is Sachin" → "Sachin", "John Smith" → "John Smith"). Always set confidence = "high" if any name is spoken.
- For village_district: extract the location name. Always set confidence = "high" if any location is spoken.
- For age: extract only the numeric digits (e.g., "sixty five" → "65", "I am 72" → "72"). If age is < 60 or ambiguous, set confidence = "low".
- For aadhaar_last4: extract exactly 4 digits (e.g., "five six seven eight" → "5678", "1 2 3 4" → "1234").
- For gender: normalize to "male" or "female".
- For has_bank_account: normalize to "yes" or "no".
- For phone_number: if user says "no", "skip", "don't have one", or "not needed", set value = "skip" and confidence = "high".
- For monthly_income_band: extract/summarize income description into clean text.
- Never guess if confidence is low — return low and the raw transcript.

Current field being collected: {slot_key}
Field description: {slot_description}
"""


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences from Gemini response if present."""
    # Remove ```json ... ``` wrapping
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


async def transcribe_and_extract(
    audio_bytes: bytes,
    slot_key: str,
    slot_description: str,
    mime_type: str = "audio/webm",
) -> dict:
    """
    Send audio to Gemini and extract the slot value + confidence.
    Returns: { transcript, value, confidence }
    """
    if MOCK_MODE:
        mock_values = {
            "intent": ("I want to apply", "yes"),
            "full_name": ("My name is John", "John"),
            "age": ("I am sixty five", "65"),
            "gender": ("Male", "male"),
            "aadhaar_last4": ("five six seven eight", "5678"),
            "village_district": ("Chennai", "Chennai"),
            "has_bank_account": ("Yes I have a bank account", "yes"),
            "monthly_income_band": ("Less than a thousand", "Less than 1000"),
            "phone_number": ("9876543210", "9876543210"),
            "confirmation": ("Yes", "yes"),
        }
        val = mock_values.get(slot_key, ("yes", "yes"))
        return {"transcript": val[0], "value": val[1], "confidence": "high"}

    print(f"[STT] Processing audio for slot '{slot_key}': {len(audio_bytes)} bytes, mime={mime_type}")

    if len(audio_bytes) < 100:
        print(f"[STT] WARNING: Audio too small ({len(audio_bytes)} bytes) — likely empty recording")
        return {"transcript": "", "value": "", "confidence": "low"}

    try:
        system_prompt = STT_EXTRACT_SYSTEM.format(
            slot_key=slot_key,
            slot_description=slot_description,
        )

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model=STT_LLM_MODEL,
            contents=[system_prompt, audio_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        raw_text = response.text
        print(f"[STT] Raw response for '{slot_key}': {repr(raw_text[:300])}")

        # Try parsing the JSON response
        cleaned = _clean_json_response(raw_text)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Aggressive fallback: try to find JSON object in the text
            print(f"[STT] JSON parse failed, attempting regex extraction...")
            match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                # Last resort: treat entire raw text as the transcript
                print(f"[STT] No JSON found. Using raw text as transcript.")
                return {
                    "transcript": raw_text.strip(),
                    "value": raw_text.strip(),
                    "confidence": "high",
                }

        transcript = result.get("transcript", "")
        value = result.get("value", "")
        confidence = result.get("confidence", "low")
        print(f"[STT] Parsed for '{slot_key}': transcript='{transcript}', value='{value}', confidence='{confidence}'")

        return {"transcript": transcript, "value": value, "confidence": confidence}

    except Exception as e:
        print(f"[STT] transcribe_and_extract ERROR for slot '{slot_key}': {type(e).__name__}: {e}")
        return {"transcript": "", "value": "", "confidence": "low"}


# ---------------------------------------------------------------------------
# LLM Dialogue Generation
# ---------------------------------------------------------------------------

DIALOGUE_SYSTEM = """You are JustSpeak, a kind and patient voice assistant helping
users apply for the Old Age Pension Scheme.

Generate natural, warm, simple English responses suitable for:
- An elderly person who may be nervous
- Being spoken aloud (not read) — use conversational English
- Being concise — 1-3 sentences maximum
- Being clear and slow — avoid complex vocabulary

Always respond in English.
"""


async def generate_agent_response(prompt: str) -> str:
    """Generate an English dialogue response for the given situation."""
    if MOCK_MODE:
        return "Sorry, please wait a moment (Mock response)."
    try:
        response = client.models.generate_content(
            model=DIALOGUE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=DIALOGUE_SYSTEM,
                temperature=0.7,
            ),
        )
        return response.text.strip()
    except Exception as e:
        return "Sorry, please wait a moment."


# ---------------------------------------------------------------------------
# Pre-built dialogue strings (fast — no LLM call needed)
# ---------------------------------------------------------------------------

GREETING_TEXT = (
    "Hello! I am JustSpeak. "
    "Today I will help you fill out the Old Age Pension application. "
    "I will ask you questions, and you just need to speak. "
    "Shall we begin?"
)

INTENT_CONFIRM_TEXT = (
    "Great. Would you like to apply for the Old Age Pension? "
    "Please say yes to continue."
)

SUBMIT_SUCCESS_PREFIX = "Your application has been successfully submitted. Your reference number is: "
SUBMIT_SUCCESS_SUFFIX = ". Please remember this number. Would you like to hear it again?"

SKIP_OFFER_TEXT = "Okay, we can skip this question for now. Let's move to the next one."
CONFIRMATION_START_TEXT = "Alright, let me read back what you told me. Please listen carefully."
CONFIRMATION_ALL_DONE_TEXT = "Wonderful! Everything looks good. Submitting your application now."


def build_confirmation_item_text(label: str, value: str) -> str:
    return f"{label}: {value}. Is this correct?"


def build_low_confidence_retry_text(slot_question: str) -> str:
    return f"Sorry, I didn't quite catch that. {slot_question}"


def build_skip_offer_text(slot_question: str) -> str:
    return (
        "I wasn't able to understand your answer after two attempts. "
        "Would you like to skip this question? Say yes to skip, "
        "or say 'again' to try once more."
    )


# ---------------------------------------------------------------------------
# TTS — Gemini 2.5 Flash native audio generation
# ---------------------------------------------------------------------------

async def synthesize_speech(text: str, lang: str = "en") -> bytes:
    """
    Generate TTS audio using Gemini Flash TTS, falling back to gTTS on quota/API errors.
    Returns PCM/WAV or MP3 audio bytes.
    """
    if MOCK_MODE:
        return _generate_silent_wav()
    try:
        response = client.models.generate_content(
            model=TTS_MODEL,
            contents=f"Read aloud verbatim: {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Aoede"   # calm, clear female voice
                        )
                    )
                ),
            ),
        )

        audio_data = response.candidates[0].content.parts[0].inline_data.data
        # Wrap raw PCM in a WAV header for browser playback
        return _wrap_pcm_as_wav(audio_data)

    except Exception as e:
        print(f"[TTS] Gemini TTS failed ({e}). Falling back to gTTS...")
        try:
            if gTTS is None:
                raise RuntimeError("gTTS package is not available")
            fp = BytesIO()
            tts = gTTS(text=text, lang=lang)
            tts.write_to_fp(fp)
            return fp.getvalue()
        except Exception as gtts_err:
            print(f"[TTS] gTTS Fallback Error: {gtts_err}. Returning silent audio.")
            return _generate_silent_wav()


def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a WAV container."""
    num_channels   = 1
    bits_per_sample = 16
    byte_rate      = sample_rate * num_channels * bits_per_sample // 8
    block_align    = num_channels * bits_per_sample // 8
    data_size      = len(pcm_bytes)

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,               # PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_bytes


def _generate_silent_wav(duration_ms: int = 500) -> bytes:
    """Minimal silent WAV fallback."""
    sample_rate     = 24000
    num_samples     = int(sample_rate * duration_ms / 1000)
    num_channels    = 1
    bits_per_sample = 16
    byte_rate       = sample_rate * num_channels * bits_per_sample // 8
    block_align     = num_channels * bits_per_sample // 8
    data_size       = num_samples * block_align

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate,
        byte_rate, block_align, bits_per_sample,
        b"data", data_size,
    )
    return header + bytes(data_size)


def audio_to_base64(audio_bytes: bytes) -> str:
    return base64.b64encode(audio_bytes).decode("utf-8")
