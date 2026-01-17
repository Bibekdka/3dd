import time
import os
import sys
import subprocess
import streamlit as st
from playwright.sync_api import sync_playwright

# Check safe mode
SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

def install_playwright_if_needed():
    if sys.platform != "win32":
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except: pass

# --- BROWSER CACHING (Speed Boost) ---
# This keeps the Playwright instance alive across Streamlit re-runs
@st.cache_resource
def get_playwright_instance():
    try: 
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True if sys.platform != "win32" else False, # Headless on Cloud, Visible on Windows
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        return browser
    except: return None

def scrape_model_page(url, debug=False):
    if SAFE_MODE: return {"error": "Safe Mode enabled."}
    
    logs = []
    
    try:
        # Get cached browser instead of launching new one
        browser = get_playwright_instance()
        if not browser: return {"error": "Browser Failed to Launch"}
        
        # New Context for every scrape (Cookies/Session isolation)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        logs.append(f"Navigating to {url}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except: pass

        # --- SAFETY BRAKE (Max Clicks) ---
        def safe_click_load_more():
            trigger_words = ["Load more", "Show more", "View all"]
            MAX_CLICKS = 5 # Safety limit to prevent freezing
            
            for trigger in trigger_words:
                clicks = 0
                while clicks < MAX_CLICKS:
                    try:
                        btns = page.get_by_text(trigger, exact=False)
                        if btns.count() > 0 and btns.first.is_visible():
                            logs.append(f"Clicking '{trigger}' ({clicks+1}/{MAX_CLICKS})...")
                            btns.first.click(timeout=1000)
                            page.wait_for_timeout(1500)
                            clicks += 1
                        else:
                            break
                    except: break

        safe_click_load_more()
        
        full_text = page.inner_text("body")
        images = page.eval_on_selector_all("img", "imgs => imgs.map(i => i.src)")
        
        page.close() # Close page, keep browser open
        context.close()
        
        return {
            "text": full_text[:10000], # Pass more text now that we have tags
            "images": list(set(images))[:25],
            "debug": logs
        }

    except Exception as e:
        return {"error": str(e), "debug": logs}
