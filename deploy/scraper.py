import sys
import subprocess
import os
import streamlit as st
from playwright.sync_api import sync_playwright

def install_playwright_if_needed():
    if sys.platform != "win32":
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except: pass

@st.cache_resource
def get_browser():
    install_playwright_if_needed()
    playwright = sync_playwright().start()
    # HEADLESS = False on Windows so you can see/solve Captchas if needed
    headless = True if sys.platform != "win32" else False
    return playwright.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])

def scrape_model_page(url):
    logs = []
    try:
        browser = get_browser()
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        
        logs.append(f"Navigating to {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # 1. TAB HUNTING (Finding Real User Photos/Comments)
        targets = ["Makes", "I Made One", "Post a Make", "User Uploads", "Comments", "Reviews"]
        for t in targets:
            try:
                elem = page.get_by_text(t, exact=False)
                if elem.count() > 0 and elem.first.is_visible():
                    logs.append(f"Clicking '{t}'...")
                    elem.first.click(timeout=1000)
                    page.wait_for_timeout(1000)
            except: pass

        # 2. SCROLLING & LOADING
        logs.append("Deep scrolling for lazy content...")
        for _ in range(5):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(500)
            
        # 3. CLICK 'LOAD MORE' (Max 5 times)
        triggers = ["Load more", "Show more", "View all"]
        for trig in triggers:
            for _ in range(5):
                try:
                    btn = page.get_by_text(trig, exact=False).first
                    if btn.is_visible():
                        btn.click(timeout=500)
                        page.wait_for_timeout(1000)
                    else: break
                except: break

        # 4. EXTRACTION
        text = page.inner_text("body")
        images = page.eval_on_selector_all("img", """
            imgs => imgs.map(i => i.src).filter(src => 
                src.startsWith('http') && i.naturalWidth > 300 && 
                !src.includes('avatar') && !src.includes('icon')
            )
        """)
        
        page.close()
        context.close()
        
        # Clean Text
        cleaned_text = "\n".join([l.strip() for l in text.splitlines() if len(l.strip()) > 20][:6000])
        
        return {"text": cleaned_text, "images": list(set(images))[:20], "debug": logs}

    except Exception as e:
        return {"error": str(e), "debug": logs}
