import time
import subprocess
import os

SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

import streamlit as st

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
    lines = text.splitlines()
    useful = [
        l for l in lines
        if len(l) > 30  # Slightly lower threshold to capture short but useful headers
        and not any(x in l.lower() for x in [
            "cookie", "privacy", "login", "sign up",
            "terms", "copyright", "javascript", "browser"
        ])
    ]
    # Increase limit to capture more context (reviews, settings often at bottom)
    return "\n".join(useful[:500])

@st.cache_data(show_spinner=False, ttl=3600)
def scrape_model_page(url, debug=False):
    if SAFE_MODE:
        return {
            "error": "Safe Mode enabled. Scraping disabled on Streamlit Cloud.",
            "debug": ["Chromium unavailable in this environment"]
        }

    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "Playwright not available in this environment"}

    logs = []
    domain = detect_domain(url)

    try:
        with sync_playwright() as p:
            # Attempt to launch browser, install if missing
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                if "Executable doesn't exist" in str(e):
                    logs.append("Installing Playwright browsers...")
                    subprocess.run(["playwright", "install", "chromium"])
                    browser = p.chromium.launch(headless=True)
                else:
                    raise e
                    
            context = browser.new_context(
                user_agent="Mozilla/5.0 Chrome/120 Safari/537.36"
            )
            page = context.new_page()

            page.goto(url, wait_until="networkidle", timeout=60000)
            logs.append("Page loaded")

            # Scroll to load lazy content
            for _ in range(5):
                page.mouse.wheel(0, 2000)
                time.sleep(1)

            # --- DOMAIN-SPECIFIC HOOKS ---
            if domain == "printables.com":
                try:
                    page.get_by_text("Comments").click(timeout=3000)
                    logs.append("Opened comments tab")
                except:
                    logs.append("No comments tab found")

            # --- TEXT ---
            text = page.inner_text("body")[:50000]

            # --- IMAGES ---
            images = page.eval_on_selector_all(
                "img",
                """
                imgs => imgs
                  .map(i => i.src)
                  .filter(src =>
                    src && src.startsWith("http") &&
                    !src.includes("icon") &&
                    !src.includes("avatar")
                  )
                """
            )

            # --- STL DOWNLOAD (AUTO) ---
            stl_links = page.eval_on_selector_all(
                "a",
                """
                links => links
                  .map(a => a.href)
                  .filter(h => h && h.endsWith(".stl"))
                """
            )

            browser.close()

            return {
                "text": text,
                "images": list(set(images))[:5],
                "stl_links": list(set(stl_links)),
                "debug": logs if debug else None
            }

    except Exception as e:
        return {"error": str(e), "debug": logs}
