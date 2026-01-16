#!/usr/bin/env python3
"""
Test script to verify scraper functionality with provided links
Standalone version without Streamlit dependency
"""
import time
import subprocess
import os

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("❌ Playwright not available!")
    exit(1)

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
        if len(l) > 30
        and not any(x in l.lower() for x in [
            "cookie", "privacy", "login", "sign up",
            "terms", "copyright", "javascript", "browser"
        ])
    ]
    return "\n".join(useful[:500])

def scrape_model_page(url, debug=False):
    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "Playwright not available"}

    logs = []
    domain = detect_domain(url)

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
            except Exception as e:
                if "Executable doesn't exist" in str(e):
                    logs.append("Installing Playwright browsers (first run)...")
                    subprocess.run(["playwright", "install", "chromium"], check=False)
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-blink-features=AutomationControlled",
                        ],
                    )
                else:
                    raise e

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()

            # Robust navigation strategy
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)  # Allow JS to hydrate
            
            logs.append("Page loaded (domcontentloaded + 5s wait)")

            # Scroll to load lazy content
            for _ in range(5):
                page.mouse.wheel(0, 2000)
                time.sleep(1)

            # Domain-specific hooks
            if domain == "printables.com":
                try:
                    page.get_by_text("Comments").click(timeout=3000)
                    logs.append("Opened comments tab")
                except:
                    logs.append("No comments tab found")

            # TEXT
            text = page.inner_text("body")[:50000]

            # IMAGES
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

            # STL DOWNLOAD (AUTO)
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


# Test URLs
test_urls = [
    "https://makerworld.com/en/models/2181944-kumiko-lamp-goma?from=recommend#profileId-2368339",
    "https://thangs.com/designer/Studio%20Loup/3d-model/Tiered%20Pen%20Holder-1495357"
]

print("=" * 80)
print("TESTING SCRAPER WITH PROVIDED LINKS")
print("=" * 80)

for i, url in enumerate(test_urls, 1):
    print(f"\n{'='*80}")
    print(f"TEST {i}/{len(test_urls)}: {url}")
    print(f"{'='*80}\n")
    
    try:
        # Test scraping
        print("🔍 Starting scrape...")
        scraped_data = scrape_model_page(url, debug=True)
        
        # Check for errors
        if "error" in scraped_data:
            print(f"❌ SCRAPING FAILED: {scraped_data['error']}")
            if scraped_data.get("debug"):
                print("\n📝 Debug Logs:")
                for log in scraped_data["debug"]:
                    print(f"  - {log}")
            continue
        
        # Display results
        print("✅ SCRAPING SUCCESSFUL!")
        
        # Text content
        cleaned_text = clean_scraped_text(scraped_data.get('text', ''))
        print(f"\n📄 TEXT CONTENT ({len(cleaned_text)} chars):")
        print(cleaned_text[:500] + "..." if len(cleaned_text) > 500 else cleaned_text)
        
        # Images
        images = scraped_data.get('images', [])
        print(f"\n🖼️ IMAGES FOUND: {len(images)}")
        for idx, img in enumerate(images[:3], 1):
            print(f"  {idx}. {img}")
        
        # STL links
        stl_links = scraped_data.get('stl_links', [])
        print(f"\n📥 STL LINKS FOUND: {len(stl_links)}")
        for idx, link in enumerate(stl_links, 1):
            print(f"  {idx}. {link}")
        
        # Debug logs
        if scraped_data.get("debug"):
            print("\n📝 Scraper Debug Logs:")
            for log in scraped_data["debug"]:
                print(f"  - {log}")
        
        print(f"\n{'='*80}")
        print(f"✅ TEST {i} COMPLETED")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("ALL TESTS COMPLETED")
print("=" * 80)
