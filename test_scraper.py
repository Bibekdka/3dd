from scraper import scrape_model_page
import json
import time

url = "https://makerworld.com/en/models/1181509-cube-perpetual-calendar#profileId-1191798"
print(f"--- STARTING ROBUST TEST ---")
print(f"Target: {url}")

start_time = time.time()
result = scrape_model_page(url, debug=True)
end_time = time.time()

print(f"\n--- SCRAINING COMPLETE ({end_time - start_time:.2f}s) ---")

if "error" in result:
    print(f"ERROR: {result['error']}")
    print("DEBUG LOGS:")
    for log in result.get('debug', []):
        print(f"[LOG] {log}")
else:
    print(f"SUCCESS!")
    print(f"Images Found: {len(result['images'])}")
    print(f"Text Length: {len(result['text'])} chars")
    print(f"STL Links: {len(result['stl_links'])}")
    
    print("\n[FIRST 5 IMAGES]")
    for img in result['images'][:5]:
        print(f"- {img}")

    print("\n[LAST 5 LOGS]")
    for log in result['debug'][-5:]:
        print(f"- {log}")
        
    print(f"\n[TEXT SNIPPET - First 500 chars]")
    print(result['text'][:500])
