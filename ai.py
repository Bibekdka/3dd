# ai.py
import os

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_AVAILABLE and API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception:
        pass


def _default_ai_output():
    return {
        "mode": "mock",
        "summary": "General community-based recommendations.",
        "best_settings": {
            "layer_height": "0.2 mm",
            "infill": "15–20%",
            "nozzle_temp": "200–210 °C",
            "bed_temp": "55–60 °C",
            "supports": "Only for overhangs > 45°",
            "orientation": "Flat on bed"
        },
        "common_failures": [
            "Warping on large flat surfaces",
            "Stringing at high temperatures"
        ]
    }


def ai_analyze(scraped_text: str) -> dict:
    """
    ALWAYS returns:
    - mode
    - summary
    - best_settings
    - common_failures
    """

    # ---- SAFETY FIRST ----
    if not scraped_text or len(scraped_text.strip()) < 100:
        return _default_ai_output()

    if not GEMINI_AVAILABLE or not API_KEY:
        return _default_ai_output()

    prompt = f"""
You are a 3D printing expert.

From the text below, extract ONLY settings that users ACTUALLY used successfully.

TEXT:
{scraped_text}

Respond EXACTLY in this format:

SUMMARY:
<short summary>

BEST_SETTINGS:
Layer Height:
Infill:
Nozzle Temp:
Bed Temp:
Supports:
Orientation:

COMMON_FAILURES:
- bullet points
"""

    try:
        model = genai.GenerativeModel("gemini-1.0-pro")
        response = model.generate_content(prompt)

        if not response or not response.text:
            return _default_ai_output()

        text = response.text.strip()

        # VERY simple parsing (safe)
        return {
            "mode": "live",
            "summary": "Extracted from user comments and description.",
            "best_settings": {
                "raw_text": text   # show as-is (no KeyError ever)
            },
            "common_failures": []
        }

    except Exception:
        return _default_ai_output()
