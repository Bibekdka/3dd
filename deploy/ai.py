import os
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except: GEMINI_AVAILABLE = False

API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_AVAILABLE and API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception: pass

def ai_analyze(prompt):
    if not GEMINI_AVAILABLE: return {"details": "Gemini Library Missing"}
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return {"details": resp.text, "summary": resp.text[:100]+"..."}
    except Exception as e:
        return {"details": f"AI Error: {e}", "summary": "Error"}

def ai_generate_tags(text):
    if not GEMINI_AVAILABLE: return "#manual"
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(f"Generate 5 hashtags (e.g. #petg #fail) for: {text[:500]}")
        return resp.text.strip()
    except: return "#error"
