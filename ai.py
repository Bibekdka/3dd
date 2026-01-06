# ai.py
import os
import time

# --- Safe import (future-proof) ---
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# --- Configure only if key exists ---
API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_AVAILABLE and API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception:
        pass


# --- Supported models (auto-fallback order) ---
GEMINI_MODELS = [
    "gemini-1.0-pro",   # stable
    "gemini-pro"        # alias fallback
]


def ai_analyze(prompt_text: str) -> dict:
    """
    Safe Gemini AI wrapper.

    Returns:
    {
        "mode": "live" | "mock" | "error",
        "analysis": str
    }
    """

    # -------- HARD FALLBACKS --------
    if not GEMINI_AVAILABLE:
        return {
            "mode": "mock",
            "analysis": "AI unavailable (Gemini SDK not installed)."
        }

    if not API_KEY:
        return {
            "mode": "mock",
            "analysis": (
                "AI key not found.\n\n"
                "Mock recommendation:\n"
                "- Use 20% infill\n"
                "- 0.2mm layer height\n"
                "- Enable supports only if needed"
            )
        }

    if not prompt_text or len(prompt_text.strip()) < 20:
        return {
            "mode": "mock",
            "analysis": "Insufficient input text for AI analysis."
        }

    # -------- TRY MODELS SAFELY --------
    last_error = None

    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)

            # Simple timeout guard
            start = time.time()
            response = model.generate_content(prompt_text)
            elapsed = time.time() - start

            if not response or not response.text:
                raise ValueError("Empty response from Gemini")

            return {
                "mode": "live",
                "analysis": response.text.strip()
            }

        except Exception as e:
            last_error = f"{model_name}: {str(e)}"
            continue

    # -------- FINAL FAILSAFE --------
    return {
        "mode": "error",
        "analysis": (
            "Gemini API failed.\n\n"
            f"Last error: {last_error}\n\n"
            "Fallback advice:\n"
            "- Reduce infill if cosmetic\n"
            "- Increase walls for strength\n"
            "- Avoid steep overhangs"
        )
    }
