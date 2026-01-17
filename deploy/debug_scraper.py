
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from scraper import scrape_model_page
from ai import ai_analyze

def test_debug():
    url = "https://www.makerworld.com/en/models/14836" # A known safe model
    print(f"--- 1. Testing Scraper on {url} ---")
    
    try:
        data = scrape_model_page(url)
        if "error" in data:
            print(f"❌ Scraper Failed: {data['error']}")
            if "debug" in data:
                print("DEBUG LOGS:")
                for l in data['debug']: print(l)
            return
        else:
            print(f"✅ Scraper Success! Text Length: {len(data['text'])}")
            print(f"Images found: {len(data['images'])}")
    except Exception as e:
        print(f"❌ CRITICAL Scraper Exception: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n--- 2. Testing AI Analysis ---")
    try:
        prompt = f"Analyze this text: {data['text'][:2000]}"
        res = ai_analyze(prompt)
        
        print(f"Verdict: {res.get('verdict')}")
        print(f"Risk: {res.get('risk_level')}")
        print(f"Summary: {res.get('summary')}")
        
        if res.get('verdict') == "ERROR":
            print("❌ AI returned ERROR verdict.")
            print(f"Warnings: {res.get('warnings')}")
        else:
             print("✅ AI Success!")
             
    except Exception as e:
        print(f"❌ CRITICAL AI Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_debug()
