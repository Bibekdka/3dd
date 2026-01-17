import os
import typing_extensions as typing
from pydantic import BaseModel, Field
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

# 1. DEFINE STRUCT
class PrintAnalysis(BaseModel):
    verdict: str = Field(description="One word verdict: GO or STOP")
    risk_level: str = Field(description="Low, Medium, or High")
    summary: str = Field(description="A 2-sentence summary of the model")
    warnings: list[str] = Field(description="List of specific failure risks found")
    settings: list[str] = Field(description="Recommended settings (Temp, Infill, etc)")
    tags: list[str] = Field(description="5 technical hashtags starting with #")

def ai_analyze(text: str) -> dict:
    """Legacy wrapper for simple analysis if needed"""
    return ai_analyze_structured(text)

def ai_analyze_structured(text: str, memory_context: str = "") -> dict:
    """
    Robust function that forces AI to return JSON, not chatty text.
    """
    if not GEMINI_AVAILABLE or not API_KEY:
        return {
            "verdict": "ERROR", 
            "risk_level": "Unknown",
            "summary": "AI not available", 
            "warnings": ["Check API Key"], 
            "settings": [], 
            "tags": []
        }

    # List of models to try in order of preference
    models_to_try = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            
            # 2. ASK FOR JSON SCHEMA
            prompt = f"""
            Analyze this 3D print model based on the text below.
            MEMORY CONTEXT: {memory_context}
            MODEL TEXT: {text[:15000]}
            
            Return the result strictly as JSON matching the schema.
            """
            
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json", 
                    response_schema=PrintAnalysis
                )
            )
            
            # 3. VALIDATE DATA
            result = PrintAnalysis.model_validate_json(response.text)
            return result.model_dump()
            
        except Exception as e:
            continue # Try next model
            
    return {
        "verdict": "ERROR", 
        "risk_level": "High",
        "summary": "Analysis Failed", 
        "warnings": ["Could not connect to AI models"], 
        "settings": [], 
        "tags": []
    }

def ai_generate_tags(text_summary: str) -> str:
    # Just a placeholder now as tags are in the struct
    return "#3dprinting"
