import time
import sys
import subprocess
import os
import random
import streamlit as st
from playwright.sync_api import sync_playwright
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Check safe mode
SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

def install_playwright_if_needed():
    if sys.platform != "win32":
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except: pass

@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def fetch_page_html(url, browser):
    """
    Isolated function just for fetching, so we can retry just this part.
    """
    page = browser.new_page(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1920, "height": 1080}
    )
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    return page

def scrape_model_page(url):
    if SAFE_MODE: return {"error": "Safe Mode enabled."}
    
    logs = []
    IS_CLOUD = sys.platform != "win32"
    if IS_CLOUD: install_playwright_if_needed()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            
            # RETRY WRAPPED FETCH
            try:
                page = fetch_page_html(url, browser)
            except Exception as e:
                browser.close()
                return {"error": f"Failed after 3 retries: {str(e)}", "debug": logs}

            logs.append(f"Navigated to {url}")

            # --- FAST SCROLL & LOAD ---
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(500)

            # Try expanding comments (Just once)
            triggers = ["Load more", "Show more", "View all", "Comments", "Makes"]
            for t in triggers:
                try:
                    btn = page.get_by_text(t, exact=False).first
                    if btn.is_visible():
                        btn.click(timeout=500)
                except: pass

            # --- EXTRACTION ---
            text = page.inner_text("body")
            
            # Smart Image Filter
            images = page.eval_on_selector_all("img", """
                imgs => imgs.map(i => i.src).filter(src => 
                    src.startsWith('http') && 
                    !src.includes('avatar') && 
                    !src.includes('icon') &&
                    !src.includes('logo')
                )
            """)
            
            browser.close()
            
            cleaned_text = "\n".join([l.strip() for l in text.splitlines() if len(l.strip()) > 30][:4000])
            
            if len(cleaned_text) < 50:
                return {"error": "Scraped content empty.", "debug": logs}

            return {
                "text": cleaned_text,
                "images": list(set(images))[:10],
                "debug": logs
            }

    except Exception as e:
        return {"error": f"Scraper Error: {str(e)}", "debug": logs}
