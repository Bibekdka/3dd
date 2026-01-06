import os
import sys
from scraper import scrape_model_page, clean_scraped_text
from app import analyze_stl

# Test 1: Bad STL Handling
print("--- Testing Bad STL ---")
bad_file = "bad_test.stl"
try:
    # Mimic app.py call for a file
    # file_path, density, cost_per_kg, infill, walls, speed_mm_s=60, nozzle_mm=0.4
    result = analyze_stl(bad_file, 1.24, 20.0, 20, 25)
    print(f"Result: {result}")
    if isinstance(result, dict) and "error" in result:
        print("SUCCESS: Error caught correctly.")
    else:
        print("FAILURE: Error not caught or unexpected format.")
except Exception as e:
    print(f"FAILURE: Exception raised instead of handled: {e}")

# Test 2: Scraper
print("\n--- Testing Scraper ---")
url = "https://www.printables.com/model/167-emergency-whistle"
try:
    data = scrape_model_page(url, debug=True)
    if "error" in data:
        print(f"FAILURE: Scraper returned error: {data['error']}")
        if "debug" in data:
            print(f"Debug Log: {data['debug']}")
    else:
        text_len = len(data.get('text', ''))
        cleaned = clean_scraped_text(data.get('text', ''))
        print(f"SUCCESS: Scraped {text_len} chars. Cleaned length: {len(cleaned)}")
        # Verify specific content if possible
        if "whistle" in cleaned.lower():
             print("SUCCESS: Found 'whistle' in scraped text.")
        else:
             print("WARNING: 'whistle' not found in text.")
        
except Exception as e:
    print(f"FAILURE: Scraper exception: {e}")
