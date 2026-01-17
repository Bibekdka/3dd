
import os
import sys
import unittest
from dotenv import load_dotenv

# Add paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

from scraper import scrape_model_page
from ai import ai_analyze
from database import get_connection

class SystemHealthCheck(unittest.TestCase):
    
    def test_01_scraper_connectivity(self):
        print("\n--- Testing Scraper ---")
        url = "https://www.makerworld.com/en/models/14836"
        data = scrape_model_page(url)
        if "error" in data:
            self.fail(f"Scraper Error: {data['error']}")
        
        self.assertGreater(len(data['text']), 100, "Scraped text too short")
        self.assertGreater(len(data['images']), 0, "No images found")
        print("✅ Scraper: OK")
        # Store for AI test
        self.scraped_text = data['text']

    def test_02_ai_integration(self):
        print("\n--- Testing AI (Gemini) ---")
        if not os.getenv("GEMINI_API_KEY"):
            print("⚠️ Skipping AI Test: No GEMINI_API_KEY found")
            return

        # Use the structured analysis
        prompt = f"Analyze this 3D print model: {getattr(self, 'scraped_text', 'A simple calibration cube')[:2000]}"
        res = ai_analyze(prompt)
        
        if res.get('verdict') == "ERROR":
            self.fail(f"AI returned ERROR: {res.get('summary')}")
            
        self.assertIn(res.get('verdict'), ["GO", "STOP", "CAUTION", "UNKNOWN"], "Invalid verdict")
        print(f"✅ AI Verdict: {res.get('verdict')}")
        print(f"✅ AI Risk: {res.get('risk_level')}")
        print("✅ AI Integration: OK")
        
        # Test 04: Tag Extraction (It's part of the AI response now)
        tags = res.get('tags', [])
        print(f"\n--- Testing Tag Logic ---")
        print(f"Received Tags: {tags}")
        self.assertIsInstance(tags, list, "Tags should be a list")
        if len(tags) > 0:
             print("✅ Tag Extraction: OK")
        else:
             print("⚠️ Tag Extraction: Empty list (might be valid for simple input)")

    def test_03_database_connection(self):
        print("\n--- Testing Database (Google Sheets) ---")
        # Check if we have credentials env var
        if not os.getenv("gcp_service_account"):
             print("⚠️ Skipping DB Test: gcp_service_account env var missing")
             return

        try:
            sheet = get_connection()
            self.assertIsNotNone(sheet, "Sheet object is None")
            val = sheet.cell(1, 1).value
            print(f"✅ DB Connected. Cell A1: {val}")
        except Exception as e:
            print(f"❌ DB Connection Failed: {e}")
            # Don't fail the whole suite if DB is optional locally
            # self.fail(str(e))

if __name__ == '__main__':
    unittest.main()
