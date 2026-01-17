import time
import os
import sys
import subprocess
import streamlit as st

# Check safe mode
SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

SUPPORTED_DOMAINS = [
    "printables.com",
    "makerworld.com",
    "thingiverse.com",
    "thangs.com"
]

def detect_domain(url):
    for d in SUPPORTED_DOMAINS:
        if d in url:
            return d
    return "generic"

def clean_scraped_text(text):
    if not text: return ""
    lines = text.splitlines()
    useful = [
        l for l in lines
        if len(l) > 30 
        and not any(x in l.lower() for x in [
            "cookie", "privacy", "login", "sign up",
            "terms", "copyright", "javascript", "browser"
        ])
    ]
    return "\n".join(useful[:500])

def install_playwright_if_needed():
    """Auto-install Playwright browsers on Linux/Cloud environments."""
    if sys.platform != "win32": # Only on Linux/Cloud
        try:
             # Check if chromium is already installed to avoid repeated downloads
             # This is a basic check; subprocess call is safer as it handles 'already installed' gracefull
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            return True
        except Exception as e:
            st.error(f"Could not install browsers: {e}")
            return False
    return True

@st.cache_data(show_spinner=False, ttl=3600)
def scrape_model_page(url, debug=False):
    if SAFE_MODE:
        return {"error": "Safe Mode enabled. Scraping disabled."}

    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "Playwright not available. Run: pip install playwright && playwright install"}

    logs = []
    domain = detect_domain(url)

    # --- DEPLOYMENT LOGIC (Smart Headless) ---
    # On Streamlit Cloud (Linux), we MUST be Headless.
    # On Local (Windows), user wants to see the browser (False).
    IS_CLOUD = sys.platform != "win32"
    USE_HEADLESS = True if IS_CLOUD else False 

    # Auto-install on cloud if typical error appears or just preemptively
    if IS_CLOUD:
        install_playwright_if_needed()

    try:
        with sync_playwright() as p:
            try:
                # Launch browser
                browser = p.chromium.launch(
                    headless=USE_HEADLESS,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage", # Critical for containerized/cloud envs
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
            except Exception as e:
                # Fallback: Try installing if launch failed (double safety)
                if "Executable doesn't exist" in str(e) and IS_CLOUD:
                    logs.append("Browser missing. Installing...")
                    install_playwright_if_needed()
                    # Retry launch once
                    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                else:
                    return {"error": f"Browser Launch Failed: {str(e)}. Try running 'playwright install' in terminal.", "debug": logs}

            # Create context
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()

            # Navigate with a long timeout
            logs.append(f"Navigating to {url}...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                logs.append(f"Navigation warning: {str(e)}")

            # Wait for page to settle
            page.wait_for_timeout(5000)

            # Scroll to trigger lazy loading
            for _ in range(5):
                page.mouse.wheel(0, 2000)
                time.sleep(0.5)

            # --- DOMAIN-SPECIFIC ACTIONS ---
            if domain == "printables.com":
                try:
                    # Try to click comments to load them
                    page.get_by_text("Comments").click(timeout=2000)
                except:
                    pass

            # --- DATA EXTRACTION ---
            text = page.inner_text("body")[:50000]

            images = page.eval_on_selector_all(
                "img",
                """
                imgs => imgs.map(i => i.src).filter(src =>
                    src && src.startsWith("http") &&
                    !src.includes("icon") && !src.includes("avatar")
                )
                """
            )

            stl_links = page.eval_on_selector_all(
                "a",
                """
                links => links.map(a => a.href).filter(h => h && h.toLowerCase().endsWith(".stl"))
                """
            )

            browser.close()

            # Validation
            if not text or len(text) < 100:
                return {"error": "Page loaded but was empty. (Bot detection blocked access?)", "debug": logs}

            return {
                "text": text,
                "images": list(set(images))[:5],
                "stl_links": list(set(stl_links)),
                "debug": logs if debug else None
            }

    except Exception as e:
        return {"error": f"Scraping Error: {str(e)}", "debug": logs}
