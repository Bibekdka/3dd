import time
import os
import sys
import subprocess
from playwright.sync_api import sync_playwright

# Check safe mode
SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

def install_playwright_if_needed():
    if sys.platform != "win32":
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except: pass

def scrape_model_page(url, status_callback=None):
    """
    Robust scraper: Launches fresh browser per request to prevent Threading Errors.
    """
    if SAFE_MODE: return {"error": "Safe Mode enabled."}
    
    logs = []
    def report(msg):
        logs.append(msg)
        if status_callback: status_callback(msg)
        print(f"[Scraper] {msg}")

    IS_CLOUD = sys.platform != "win32"
    if IS_CLOUD: install_playwright_if_needed()

    try:
        report("🚀 Launching secure browser...")
        
        # NO CACHE HERE - Critical for Render stability
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            report(f"🌐 Navigating to {url}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1000)
            except Exception as e:
                report(f"⚠️ Navigation warning: {e}")

            report("🔍 Scanning technical data...")
            # Click load more to get comments (Vital for AI Analysis)
            triggers = ["Load more", "Show more", "View all", "Comments"]
            for t in triggers:
                try:
                    btn = page.get_by_text(t, exact=False).first
                    if btn.is_visible():
                        btn.click(timeout=500)
                        page.wait_for_timeout(200)
                except: pass

            text = page.inner_text("body")
            
            # Filter for useful images
            images = page.eval_on_selector_all("img", """
                imgs => imgs.map(i => i.src).filter(src => 
                    src.startsWith('http') && 
                    !src.includes('avatar') && 
                    !src.includes('icon') &&
                    !src.includes('logo') &&
                    i.naturalWidth > 200
                )
            """)
            
            browser.close()
            
            # Limit text size for AI
            cleaned_text = "\n".join([l.strip() for l in text.splitlines() if len(l.strip()) > 30][:10000])
            
            report("✅ Extraction complete.")
            return {
                "text": cleaned_text,
                "images": list(set(images))[:10],
                "debug": logs
            }

    except Exception as e:
        return {"error": str(e), "debug": logs}
