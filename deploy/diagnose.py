
import sys
import os
import time
from datetime import datetime

# --- IMPORT YOUR MODULES ---
print("🔌 Importing modules...")
try:
    import ai
    print("✅ ai.py found")
except ImportError:
    print("❌ CRITICAL: ai.py missing")

try:
    import scraper
    print("✅ scraper.py found")
except ImportError as e:
    print(f"❌ CRITICAL: scraper.py missing: {e}")

try:
    import database
    print("✅ database.py found")
except ImportError:
    print("❌ CRITICAL: database.py missing")

print("-" * 40)

def test_ai():
    print("\n🤖 TESTING AI INTEGRATION (Gemini)...")
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️  WARNING: GEMINI_API_KEY not found in environment variables.")
    
    start = time.time()
    try:
        # Test basic analysis
        result = ai.ai_analyze("This is a test prompt. Reply with 'AI is working'.")
        duration = time.time() - start
        
        if result.get("summary") and "Analysis unavailable" not in result["summary"]:
            print(f"✅ AI Connection Successful ({duration:.2f}s)")
            print(f"   Response Preview: {result['summary'][:50]}...")
        else:
            print("❌ AI Failed: returned fallback response.")
            print(f"   Detail: {result}")
    except Exception as e:
        print(f"❌ AI Exception: {e}")

def test_scraper():
    print("\n🕵️ TESTING WEB SCRAPER (Playwright)...")
    test_url = "https://www.printables.com/model/123-test" # Arbitrary URL to test connection
    
    start = time.time()
    try:
        # We assume scrape_model_page exists in scraper.py
        data = scraper.scrape_model_page(test_url)
        duration = time.time() - start
        
        if "error" in data:
            # It's okay if it fails to find content, but the BROWSER should launch
            print(f"⚠️ Scraper ran but returned error: {data['error']}")
            print("   (This might be normal if the URL is invalid, but Playwright launched.)")
        else:
            print(f"✅ Scraper Successful ({duration:.2f}s)")
            print(f"   Text extracted: {len(data['text'])} chars")
            print(f"   Images found: {len(data['images'])}")
    except Exception as e:
        print(f"❌ Scraper Exception: {e}")
        print("   HINT: Did you run 'playwright install'?")

def test_database():
    print("\n💾 TESTING DATABASE (Google Sheets / SQLite)...")
    try:
        # 1. Init
        database.init_db()
        print("   Database initialized.")
        
        # 2. Write Test
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry_name = f"DIAGNOSTIC_TEST_{timestamp}"
        success = database.add_entry(
            entry_type="TEST",
            name=entry_name,
            details="Running diagnose.py health check",
            cost=0.0,
            ai_summary="System Test",
            tags="#test #debug",
            full_json="{}"
        )
        
        if success:
            print("✅ Write Access: Success")
        else:
            print("❌ Write Access: Failed")
            return

        # 3. Read Test
        df = database.load_history()
        if not df.empty:
            # Check if our entry exists
            found = df[df['name'] == entry_name]
            if not found.empty:
                print("✅ Read Access: Success (Found newly created entry)")
            else:
                print("⚠️ Read Access: DataFrame loaded, but couldn't find the new entry immediately.")
        else:
            print("⚠️ Read Access: Returned empty DataFrame.")
            
    except Exception as e:
        print(f"❌ Database Exception: {e}")
        if "gspread" in str(e):
            print("   HINT: Check your 'gcp_service_account' secrets or JSON key.")

def test_tag_logic():
    print("\n🏷️ TESTING TAG EXTRACTION...")
    sample_text = """
    This is a 3D print of a dragon. 
    It requires PLA filament and a 0.4mm nozzle. 
    Warning: The wings might warp.
    """
    
    try:
        # Test the regex/AI tag generator
        tags = ai.ai_generate_tags(sample_text)
        print(f"   Input text length: {len(sample_text)}")
        print(f"   Generated Tags: {tags}")
        
        if tags and "#" in tags:
            print("✅ Tag Logic: Success")
        elif "manual" in tags:
            print("⚠️ Tag Logic: Returned fallback (AI might be offline)")
        else:
            print("❌ Tag Logic: Returned unexpected format")
            
    except Exception as e:
        print(f"❌ Tag Logic Exception: {e}")

if __name__ == "__main__":
    print("==========================================")
    print("   3D PRINT COMPANION - HEALTH CHECK      ")
    print("==========================================")
    
    test_ai()
    test_scraper()
    test_database()
    test_tag_logic()
    
    print("\n==========================================")
    print("   DIAGNOSTIC COMPLETE                    ")
    print("==========================================")
