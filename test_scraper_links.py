#!/usr/bin/env python3
"""
Test script to verify scraper functionality with provided links
"""
from scraper import scrape_model_page, clean_scraped_text
from ai import ai_analyze
import json

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
        
        # Test AI analysis
        print("\n🧠 TESTING AI ANALYSIS...")
        ai_prompt = f"""
Analyze this scraped 3D model page content:

RAW TEXT:
{cleaned_text[:2000]}

TASKS:
1. Extract Key Print Settings (Layer height, Infill, Walls, Supports) if mentioned.
2. Summarize the Model Description.
3. Summarize User Reviews/Sentiment (look for "Comments" or "Reviews" sections in text).
4. Identify any warnings or common print failures mentioned.

Format nicely with Markdown.
"""
        ai_result = ai_analyze(ai_prompt)
        
        print(f"\n📊 AI SUMMARY:")
        print(f"  {ai_result['summary']}")
        print(f"\n📋 AI DETAILS:")
        print(ai_result['details'])
        
        # Calculate metrics (simulated)
        print("\n💰 METRICS CALCULATION:")
        print("  [Calculator would process scraped data here]")
        print(f"  - Images available for preview: {len(images)}")
        print(f"  - STL files ready for download: {len(stl_links)}")
        print(f"  - AI recommendations ready: Yes")
        
        print(f"\n{'='*80}")
        print(f"✅ TEST {i} COMPLETED SUCCESSFULLY")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("ALL TESTS COMPLETED")
print("=" * 80)
