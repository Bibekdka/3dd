from scraper import scrape_model_page
import json

url = "https://makerworld.com/en/models/1181509-cube-perpetual-calendar#profileId-1191798"
print(f"Testing Scraper on: {url}")

result = scrape_model_page(url, debug=True)

if "error" in result:
    print(f"ERROR: {result['error']}")
    print("DEBUG LOGS:")
    for log in result.get('debug', []):
        print(f"- {log}")
else:
    print(f"Success! Found {len(result['images'])} images and {len(result['text'])} chars of text.")
    print(f"STL Links: {len(result['stl_links'])}")
    print("First 5 Images:")
    for img in result['images'][:5]:
        print(f"- {img}")
    
    print("\nDEBUG LOGS:")
    for log in result['debug']:
        print(f"- {log}")
