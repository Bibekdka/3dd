from scraper import scrape_model_page

url = "https://www.thingiverse.com/thing:7239501"

print(f"Testing URL: {url}")
try:
    result = scrape_model_page(url, debug=True)
    if "error" in result:
        print("ERROR:", result["error"])
        if "debug" in result:
            print("DEBUG LOGS:", result["debug"])
    else:
        print("SUCCESS")
        print("Images found:", len(result.get("images", [])))
        print("Text length:", len(result.get("text", "")))
        print("STL Links:", result.get("stl_links", []))
except Exception as e:
    print(f"EXCEPTION: {e}")
