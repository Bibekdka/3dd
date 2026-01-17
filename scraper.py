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
    priority_words = [
        "filament", "pla", "silk", "asa", "tpu", "95a", "matte", "gradient", "wood", "carbon fiber", "petg",
        "0.6", "0.2", "nozzle", "pei", "sheet", "enclosure", "brim", "raft", "ams", "mmu", "multi-color",
        "spaghetti", "clog", "adhesion", "warped", "layer shift", "snapped", "brittle", "stringing",
        "easy", "hard", "nightmare", "perfect", "kid", "gift", "love", "waste", "failed", "success"
    ]
    useful = []
    for l in lines:
        stripped = l.strip()
        is_priority = any(w in stripped.lower() for w in priority_words)
        # Relaxed filtering: Keep almost everything if meaningful
        if len(stripped) > 20 or is_priority:
            useful.append(stripped)
            
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
    USE_HEADLESS = True  

    if IS_CLOUD: install_playwright_if_needed()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=USE_HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                # ESSENTIAL: User Agent to receive Desktop Version
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            logs.append(f"Navigating to {url}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except: pass
            
            page.wait_for_timeout(3000) # Initial load wait

            # --- ROBUST TAB HUNTING ---
            def activate_content():
                logs.append("Hunting for tabs (Makes/Comments)...")
                
                # Targets: Mix of exact case and likely variations
                targets = ["Makes", "Comments", "Post a Make", "User Uploads", "Reviews", "Print Profiles"]
                
                for t in targets:
                    try:
                        # Use first() with looser visibility constraints if needed
                        elem = page.get_by_text(t, exact=False)
                        count = elem.count()
                        
                        if count > 0:
                            # Try clicking the first visible one
                            for i in range(count):
                                if elem.nth(i).is_visible():
                                    logs.append(f"Found visual tab: '{t}'. Clicking...")
                                    elem.nth(i).click(timeout=2000)
                                    page.wait_for_timeout(2000)
                                    break
                    except: pass
                
                # Deep Scroll for Lazy Loading (Essential for MakerWorld)
                logs.append("Scrolling deep for lazy content...")
                for _ in range(8): 
                    page.mouse.wheel(0, 4000) 
                    page.wait_for_timeout(1000)
                
                # "Load More" Expansion (Recursive)
                trigger_words = ["Load more", "Show more", "View all", "See more"]
                max_clicks = 10 # Safety limit
                click_count = 0
                for trigger in trigger_words:
                    while click_count < max_clicks: # Prevent infinite loops
                        try:
                            btns = page.get_by_text(trigger, exact=False)
                            if btns.count() > 0 and btns.first.is_visible():
                                logs.append(f"Clicking '{trigger}' ({click_count+1}/{max_clicks})...")
                                btns.first.click(timeout=1000)
                                page.wait_for_timeout(2000)
                                click_count += 1
                            else:
                                break
                        except: break

            activate_content()

            full_text = page.inner_text("body")
            
            # --- IMAGE EXTRACTION (Unlimited + Smart Filter) ---
            images = page.eval_on_selector_all(
                "img",
                """
                imgs => imgs.map(i => {
                    return {
                        src: i.src, 
                        width: i.naturalWidth, 
                        height: i.naturalHeight
                    }
                }).filter(img => 
                    img.src.startsWith('http') && 
                    img.width > 200 && img.height > 200 &&     
                    !img.src.includes('avatar') &&             
                    !img.src.includes('icon') &&               
                    !img.src.includes('logo') &&
                    (img.width + 50 > img.height && img.height + 50 > img.width ? false : true) // Filter out pure squares (avatars)
                ).map(i => i.src)
                """
            )

            stl_links = page.eval_on_selector_all("a", "links => links.map(a => a.href).filter(h => h && h.toLowerCase().endsWith('.stl'))")

            browser.close()
            cleaned_text = clean_scraped_text(full_text)
            
            return {
                "text": cleaned_text,
                "images": list(set(images)), 
                "stl_links": list(set(stl_links)),
                "debug": logs
            }

    except Exception as e:
        return {"error": str(e), "debug": logs}
