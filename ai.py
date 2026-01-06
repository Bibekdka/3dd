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


def ai_analyze(text: str) -> dict:
    """
    SAFE AI wrapper.
    NEVER crashes.
    NEVER changes shape unexpectedly.
    """

    fallback = {
        "summary": "General community-based recommendations.",
        "details": (
            "- Layer height: 0.2 mm\n"
            "- Infill: 15–20%\n"
            "- Nozzle temp: 200–210 °C\n"
            "- Bed temp: 55–60 °C\n"
            "- Supports: Only if needed\n"
            "- Orientation: Flat on bed\n"
        )
    }

    if not text or len(text.strip()) < 50:
        return fallback

    if not GEMINI_AVAILABLE or not API_KEY:
        return fallback

    try:
        model = genai.GenerativeModel("gemini-1.0-pro")
        response = model.generate_content(text)

        if not response or not response.text:
            return fallback

        return {
            "summary": "Extracted from user comments and descriptions.",
            "details": response.text.strip()
        }

    except Exception:
        return fallback
