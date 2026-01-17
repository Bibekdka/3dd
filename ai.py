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
    except Exception: pass

def ai_analyze(text: str) -> dict:
    fallback = {"summary": "Analysis unavailable", "details": "Check API Key"}
    
    if not GEMINI_AVAILABLE or not API_KEY: return fallback

    try:
        model = genai.GenerativeModel("gemini-1.5-flash") # Flash is faster/cheaper
        response = model.generate_content(text)
        if not response or not response.text: return fallback
        return {"summary": "AI Analysis", "details": response.text.strip()}
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return fallback

def ai_generate_tags(text_summary: str) -> str:
    """
    New: Generates hashtags for the database (Auto-Tagging).
    """
    if not GEMINI_AVAILABLE or not API_KEY: return "#manual #check"
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"Generate 5 short technical hashtags for this 3D print description. Output ONLY the tags (e.g., #petg #articulated #vase-mode). Text: {text_summary[:500]}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return "#3dprint #model"
