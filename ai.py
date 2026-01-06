import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def ai_analyze(prompt_text):
    if not os.getenv("GEMINI_API_KEY"):
        return {
            "mode": "mock",
            "analysis": "Mock AI: Increase infill for strength."
        }

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt_text)
        return {
            "mode": "live",
            "analysis": response.text
        }
    except Exception as e:
        return {
            "mode": "error",
            "analysis": str(e)
        }
