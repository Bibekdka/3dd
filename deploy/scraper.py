
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
    Scrapes a page with real-time status updates.
    status_callback: A function like st.write() to report progress.
    """
    if SAFE_MODE: return {"error": "Safe Mode enabled."}
    
    logs = []
    
    # Helper to report status
    def report(msg):
        logs.append(msg)
        if status_callback:
            status_callback(msg)
        print(f"[Scraper] {msg}")

    IS_CLOUD = sys.platform != "win32"
    if IS_CLOUD: install_playwright_if_needed()

    try:
        report("🚀 Launching Browser...")
        
        # CRITICAL FIX: No Caching. Launch fresh browser for every request to avoid Threading Error.
        # CONTEXT MANAGER: Launches and Closes browser safely in the CURRENT thread.
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, # Always headless on server
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
                page.wait_for_timeout(2000) # Wait for JS to settle
            except Exception as e:
                report(f"⚠️ Navigation warning: {e}")

            # --- SAFETY BRAKE (Max Clicks) ---
            report("🖱️ Expanding content (Comments/Makes)...")
            trigger_words = ["Load more", "Show more", "View all", "Comments"]
            MAX_CLICKS = 3 
            
            # --- SAFETY BRAKE (Fixed Logic) ---
            report("🖱️ Expanding content (Comments/Makes)...")
            trigger_words = ["Load more", "Show more", "View all", "Comments"]
            
            # Simplified Logic: Try each trigger ONCE, wait briefly.
            # If it fails, strictly move on. No infinite loops.
            for trigger in trigger_words:
                try:
                    # Specific timeout for finding element
                    btn = page.get_by_text(trigger, exact=False).first
                    if btn.is_visible():
                        report(f"   ↳ Clicking '{trigger}'...")
                        btn.click(timeout=2000) # Strict click timeout
                        page.wait_for_timeout(1000)
                except Exception:
                    # Ignore any click/find errors and continue
                    continue

            report("📝 Extracting text and images...")
            full_text = page.inner_text("body")
            
            # Smart Image Filter
            images = page.eval_on_selector_all(
                "img", 
                """
                imgs => imgs.map(i => i.src).filter(src => 
                    src.startsWith('http') && 
                    !src.includes('avatar') && 
                    !src.includes('icon') &&
                    !src.includes('logo')
                )
                """
            )
            
            browser.close()
            report(f"✅ Done! Found {len(images)} images.")
            
            # Clean Text
            cleaned_text = "\n".join([l.strip() for l in full_text.splitlines() if len(l.strip()) > 20][:6000])
            
            return {
                "text": cleaned_text,
                "images": list(set(images))[:20],
                "debug": logs
            }

    except Exception as e:
        report(f"❌ Critical Error: {str(e)}")
        return {"error": str(e), "debug": logs}
