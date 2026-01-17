import time
import os
import sys
import subprocess
import re

SAFE_MODE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("PLAYWRIGHT NOT INSTALLED")

def clean_scraped_text(text):
    if not text: return ""
    return text[:1000] # Return first 1000 chars for debug

def install_playwright_if_needed():
    if sys.platform != "win32":
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except: pass

def scrape_model_page(url):
    IS_CLOUD = sys.platform != "win32"
    USE_HEADLESS = True 

    if IS_CLOUD: install_playwright_if_needed()

    try:
        with sync_playwright() as p:
            print("Launching Browser...")
            # ADDING USER AGENT to avoid bot detection
            browser = p.chromium.launch(
                headless=USE_HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            print(f"Navigating to {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000) # Wait longer for JS

            print(f"Page Title: {page.title()}")
            
            # DEBUG: Print all potential tabs
            print("Checking page content...")
            content = page.inner_text("body")
            print(f"Body length: {len(content)}")
            if len(content) < 500:
                print("SHORT CONTENT DETECTED. Page might not have loaded.")
                print("BODY START:", content[:200])

            # Try to find tabs again
            targets = ["Makes", "Comments", "Print Profiles", "Reviews"]
            for t in targets:
                cnt = page.get_by_text(t, exact=False).count()
                print(f"Target '{t}': Found {cnt} instances")

            browser.close()
            return {"title": page.title(), "content_len": len(content)}

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    url = "https://makerworld.com/en/models/1181509-cube-perpetual-calendar#profileId-1191798"
    scrape_model_page(url)
