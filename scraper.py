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
            
    # USER REQUEST: "comments to be unlimited"
    return "\n".join(useful)

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
            
            # --- 2. ROBUST NAVIGATION (The Fix) ---
            def activate_makes_tab():
                logs.append("Hunting for User Photos (Makes/Comments)...")
                
                # 1. DEFINE TARGETS
                # These are the text labels usually found on tabs
                targets = [
                    "Makes",           # Thingiverse / Printables
                    "I Made One",      # Thingiverse
                    "Post a Make",     # General
                    "User Uploads",    # General
                    "Comments",        # MakerWorld / General
                    "Reviews",         # Thangs / General
                    "Print Profiles"   # MakerWorld (Often contains photos)
                ]
                
                tab_found = False
                
                # 2. CLICK THE TAB
                for t in targets:
                    try:
                        # "by_text" ignores random IDs. exact=False matches "Comments (24)"
                        elem = page.get_by_text(t, exact=False)
                        
                        if elem.count() > 0 and elem.first.is_visible():
                            logs.append(f"Found tab: '{t}'. Clicking...")
                            elem.first.click(timeout=2000)
                            page.wait_for_timeout(2000) 
                            tab_found = True
                            
                            if "Comments" in t:
                                logs.append("In Comments section. Scanning for image attachments...")
                            break 
                    except: 
                        pass
                
                if not tab_found:
                    logs.append("No specific 'Makes' tab found. relying on main page scroll.")

                # 3. FORCE LOAD HIDDEN IMAGES
                logs.append("scrolling deep to trigger lazy-loading...")
                for _ in range(6): 
                    page.mouse.wheel(0, 5000) 
                    page.wait_for_timeout(1000)
                
                # 4. EXPAND "LOAD MORE" BUTTONS
                trigger_words = ["Load more", "Show more", "View all", "See more"]
                for trigger in trigger_words:
                    try:
                        btns = page.get_by_text(trigger, exact=False)
                        if btns.count() > 0:
                            logs.append(f"Clicking '{trigger}' to reveal more photos...")
                            btns.first.click(timeout=1000)
                            page.wait_for_timeout(2000)
                    except: pass

            activate_makes_tab()

            full_text = page.inner_text("body")
            
            # --- 3. EXTRACT PHOTOS (Advanced Filter) ---
            images = page.eval_on_selector_all(
                "img",
                """
                imgs => imgs.map(i => {
                    return {
                        src: i.src, 
                        width: i.naturalWidth, 
                        height: i.naturalHeight,
                        alt: i.alt || ""
                    }
                }).filter(img => 
                    // HEURISTICS TO FIND "REAL" PHOTOS:
                    img.src.startsWith('http') && 
                    img.width > 200 && img.height > 200 &&     // Ignore tiny icons
                    !img.src.includes('avatar') &&             // Ignore user profile pics
                    !img.src.includes('icon') &&               // Ignore UI icons
                    !img.src.includes('logo') &&               // Ignore site logos
                    (img.width > img.height || img.height > img.width) // Ignore perfect squares (often generic avatars)
                ).map(i => i.src)
                """
            )

            stl_links = page.eval_on_selector_all("a", "links => links.map(a => a.href).filter(h => h && h.toLowerCase().endsWith('.stl'))")

            browser.close()
            cleaned_text = clean_scraped_text(full_text)
            
            # USER REQUEST: "imags to unlimited"
            return {
                "text": cleaned_text,
                "images": list(set(images)), 
                "stl_links": list(set(stl_links)),
                "debug": logs
            }

    except Exception as e:
        return {"error": str(e), "debug": logs}
