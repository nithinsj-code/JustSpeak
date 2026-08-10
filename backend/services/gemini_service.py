"""
Gemini Service — STT, LLM dialogue, and TTS using the new google-genai SDK.
Uses a single GEMINI_API_KEY for everything.
"""

import base64
import json
import os

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Model IDs
STT_LLM_MODEL  = "gemini-2.5-flash"
TTS_MODEL      = "gemini-2.5-flash-preview-tts"
DIALOGUE_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# STT + Slot Extraction (single call: audio → JSON)
# ---------------------------------------------------------------------------

STT_EXTRACT_SYSTEM = """You are a Tamil speech recognition and form data extraction assistant.
The user is a non-literate elderly Tamil speaker applying for the Tamil Nadu Old Age Pension Scheme.

You will receive an audio clip of the user's spoken response and context about what field is being collected.

Return ONLY a valid JSON object with these exact fields:
{
  "transcript": "<verbatim Tamil/English transcription of what was said>",
  "extracted_value": "<the clean extracted value for the field, normalized>",
  "confidence": "high or low",
  "reasoning": "<brief English explanation of your confidence>"
}

Rules:
- confidence = "high" if you clearly understood the spoken value and it fits the expected field
- confidence = "low" if audio was unclear, ambiguous, noisy, or value does not make sense for the field
- For age: extract only the number (e.g., "அறுபத்தைந்து" → "65")
- For aadhaar_last4: extract exactly 4 digits (e.g., "ஐந்து ஆறு ஏழு எட்டு" → "5678")
- For gender: normalize to "male" or "female"
- For has_bank_account: normalize to "yes" or "no"
- For phone_number: if user says "தேவையில்லை" or "no", extracted_value = "skip"
- Never guess if confidence is low — return low and the raw transcript

Current field being collected: {slot_key}
Field description: {slot_description}
"""


async def transcribe_and_extract(
    audio_bytes: bytes,
    slot_key: str,
    slot_description: str,
    mime_type: str = "audio/webm",
) -> dict:
    """
    Send audio to Gemini and extract the slot value + confidence.
    Returns: { transcript, extracted_value, confidence, reasoning }
    """
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

        result = json.loads(response.text)
        return {
            "transcript":       result.get("transcript", ""),
            "extracted_value":  result.get("extracted_value", ""),
            "confidence":       result.get("confidence", "low"),
            "reasoning":        result.get("reasoning", ""),
        }

    except Exception as e:
        return {
            "transcript":      "",
            "extracted_value": "",
            "confidence":      "low",
            "reasoning":       f"Error: {str(e)}",
        }


# ---------------------------------------------------------------------------
# LLM Dialogue Generation
# ---------------------------------------------------------------------------

DIALOGUE_SYSTEM = """You are JustSpeak (ஒன்று பேசு), a kind and patient voice assistant helping
elderly Tamil-speaking users apply for the Tamil Nadu Old Age Pension Scheme.

Generate natural, warm, simple Tamil responses suitable for:
- A non-literate elderly person who may be nervous
- Being spoken aloud (not read) — use conversational Tamil, not formal written Tamil
- Being concise — 1-3 sentences maximum
- Being clear and slow — avoid complex vocabulary

Always respond in Tamil script unless the context specifically asks for English.
"""


async def generate_agent_response(prompt: str) -> str:
    """Generate a Tamil dialogue response for the given situation."""
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
        return "மன்னிக்கவும், சிறிது நேரம் காத்திருங்கள்."


# ---------------------------------------------------------------------------
# Pre-built dialogue strings (fast — no LLM call needed)
# ---------------------------------------------------------------------------

GREETING_TEXT = (
    "வணக்கம்! நான் ஒன்று பேசு. "
    "இன்று நாம் உங்களுக்கு முதியோர் நல உதவித்தொகை விண்ணப்பம் பூர்த்தி செய்ய உதவுவோம். "
    "நான் கேள்விகள் கேட்பேன், நீங்கள் பேசினால் போதும். "
    "ஆரம்பிக்கலாமா?"
)

INTENT_CONFIRM_TEXT = (
    "நல்லது. முதியோர் நல உதவித்தொகைக்கு விண்ணப்பிக்க விரும்புகிறீர்களா? "
    "ஆம் என்று சொல்லுங்கள்."
)

SUBMIT_SUCCESS_PREFIX = "உங்கள் விண்ணப்பம் வெற்றிகரமாக சமர்ப்பிக்கப்பட்டது. உங்கள் குறிப்பு எண்: "
SUBMIT_SUCCESS_SUFFIX = ". இந்த எண்ணை நினைவில் வைத்துக்கொள்ளுங்கள். மீண்டும் கேட்க வேண்டுமா?"

SKIP_OFFER_TEXT = "சரி, இந்த கேள்வியை இப்போது தவிர்க்கலாம். அடுத்த கேள்விக்கு செல்வோம்."
CONFIRMATION_START_TEXT = "நல்லது, இப்போது நீங்கள் சொன்னதை ஒரு முறை திரும்ப சொல்கிறேன், கவனமாக கேளுங்கள்."
CONFIRMATION_ALL_DONE_TEXT = "அருமை! எல்லாம் சரி. இப்போது விண்ணப்பம் அனுப்புகிறோம்."


def build_confirmation_item_text(label: str, value: str) -> str:
    return f"{label}: {value}. இது சரிதானா?"


def build_low_confidence_retry_text(slot_question: str) -> str:
    return f"மன்னிக்கவும், சரியாக புரியவில்லை. {slot_question}"


def build_skip_offer_text(slot_question: str) -> str:
    return (
        "இந்த கேள்விக்கு இரண்டு முறை பதில் புரியவில்லை. "
        "இதை தவிர்க்க வேண்டுமா? ஆம் என்று சொல்லுங்கள், "
        "அல்லது மீண்டும் முயற்சிக்க 'மீண்டும்' என்று சொல்லுங்கள்."
    )


# ---------------------------------------------------------------------------
# TTS — Gemini 2.5 Flash native audio generation
# ---------------------------------------------------------------------------

async def synthesize_speech(text: str, lang: str = "ta") -> bytes:
    """
    Generate TTS audio using Gemini 2.5 Flash TTS.
    Returns raw PCM/WAV audio bytes.
    Falls back to a silent WAV on error.
    """
    try:
        response = client.models.generate_content(
            model=TTS_MODEL,
            contents=text,
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
        print(f"[TTS] Error: {e}. Returning silent audio.")
        return _generate_silent_wav()


def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a WAV container."""
    import struct
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
    import struct
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
