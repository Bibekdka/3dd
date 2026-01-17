import time
import os
import sys
import subprocess
import streamlit as st
import re

# Check safe mode
SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

SUPPORTED_DOMAINS = ["printables.com", "makerworld.com", "thingiverse.com", "thangs.com"]

def detect_domain(url):
    for d in SUPPORTED_DOMAINS:
        if d in url: return d
    return "generic"

def clean_scraped_text(text):
    if not text: return ""
    lines = text.splitlines()
    
    # 1. EXPANDED KEYWORD SEARCHING (The "Trigger Words")
    priority_words = [
        # Filament Specifics
        "pla+", "silk", "asa", "tpu", "95a", "matte", "gradient", "wood", "carbon fiber", "petg",
        # Hardware Specifics
        "0.6", "0.2", "nozzle", "pei", "sheet", "enclosure", "brim", "raft", "ams", "mmu", "multi-color",
        # Failure Modes
        "spaghetti", "clog", "adhesion", "warped", "layer shift", "snapped", "brittle", "stringing",
        # Vibe / Sentiment
        "easy", "hard", "nightmare", "perfect", "kid", "gift", "love", "waste", "failed", "success"
    ]
    
    useful = []
    for l in lines:
        stripped = l.strip()
        is_priority = any(w in stripped.lower() for w in priority_words)
        
        # Keep if it's long enough OR if it contains a trigger word
        if (len(stripped) > 20 or is_priority) and not any(x in stripped.lower() for x in ["cookie", "privacy", "login", "sign up"]):
            useful.append(stripped)
            
    return "\n".join(useful[:6000]) # Increased limit for deeper context

def install_playwright_if_needed():
    if sys.platform != "win32":
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except: pass

@st.cache_data(show_spinner=False, ttl=3600)
def scrape_model_page(url, debug=False):
    if SAFE_MODE: return {"error": "Safe Mode enabled."}
    if not PLAYWRIGHT_AVAILABLE: return {"error": "Playwright not available."}

    logs = []
    IS_CLOUD = sys.platform != "win32"
    USE_HEADLESS = True if IS_CLOUD else False 
    if IS_CLOUD: install_playwright_if_needed()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=USE_HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            logs.append(f"Navigating to {url}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except: pass
            
            # --- 2. PRIORITIZE USER-GENERATED CONTENT (UGC) ---
            def activate_makes_tab():
                # We prioritize tabs that contain "Makes" or "Uploads" to get real photos
                targets = ["Makes", "I Made One", "Post a Make", "User Uploads", "Comments"]
                
                for t in targets:
                    try:
                        elem = page.get_by_text(t, exact=False)
                        if elem.count() > 0 and elem.first.is_visible():
                            logs.append(f"Clicking '{t}' to find real user photos...")
                            elem.first.click(timeout=1500)
                            page.wait_for_timeout(2000) 
                    except: pass
                
                # Deep scroll to load lazy images
                for _ in range(6):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1000)
                
                # Expand "Load More" to get past the first 5 results
                try:
                    page.get_by_text("Load more", exact=False).first.click(timeout=1000)
                    page.wait_for_timeout(1500)
                except: pass

            activate_makes_tab()

            full_text = page.inner_text("body")
            
            # Smart Image Extraction: Filter out small icons/avatars
            images = page.eval_on_selector_all(
                "img",
                """
                imgs => imgs.map(i => {
                    return {src: i.src, width: i.naturalWidth, height: i.naturalHeight}
                }).filter(img => 
                    img.src.startsWith('http') && 
                    img.width > 300 && img.height > 300 && 
                    !img.src.includes('avatar') && !img.src.includes('icon')
                ).map(i => i.src)
                """
            )

            stl_links = page.eval_on_selector_all("a", "links => links.map(a => a.href).filter(h => h && h.toLowerCase().endsWith('.stl'))")

            browser.close()
            cleaned_text = clean_scraped_text(full_text)
            
            return {
                "text": cleaned_text,
                "images": list(set(images))[:25], 
                "stl_links": list(set(stl_links)),
                "debug": logs
            }

    except Exception as e:
        return {"error": str(e), "debug": logs}
