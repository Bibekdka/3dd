
import os
import io
import requests
import typing_extensions as typing
from PIL import Image
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
    """Legacy wrapper for simple text analysis"""
    return ai_analyze_multimodal(text, [])

def ai_generate_tags(text_summary: str) -> str:
    return "#3dprinting"

def ai_analyze_multimodal(text: str, image_urls: list[str] = [], memory_context: str = "") -> dict:
    """
    Robust function that accepts Text + Images and returns structured JSON.
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
    # We prioritize Flash for Multimodal speed/cost
    models_to_try = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro"]

    # --- 1. DOWNLOAD IMAGES ---
    images_to_send = []
    if image_urls:
        for url in image_urls[:3]: # Max 3 images
            try:
                resp = requests.get(url, timeout=3)
                if resp.status_code == 200:
                    img = Image.open(io.BytesIO(resp.content))
                    images_to_send.append(img)
            except Exception:
                continue

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            
            # --- 2. CONSRUCT PROMPT ---
            # We mix text and images in a list
            prompt_parts = [
                f"""
                You are a sophisticated 3D Printing Expert AI.
                Analyze the provided 3D model images and description.
                
                USER MEMORY (Failures): {memory_context}
                MODEL DESCRIPTION: {text[:15000]}
                
                Look for:
                1. Thin walls or fragile features (Visual check).
                2. Overhangs needing support (Visual check).
                3. Text description warnings.
                
                Return strictly JSON.
                """
            ]
            # Add images to prompt
            prompt_parts.extend(images_to_send)
            
            # --- 3. GENERATE ---
            response = model.generate_content(
                prompt_parts,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json", 
                    response_schema=PrintAnalysis
                )
            )
            
            # --- 4. VALIDATE ---
            result = PrintAnalysis.model_validate_json(response.text)
            res_dict = result.model_dump()
            
            # Append a flag so user knows images were used
            if images_to_send:
                res_dict['summary'] += " (👁️ Visually Analyzed)"
                
            return res_dict
            
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
