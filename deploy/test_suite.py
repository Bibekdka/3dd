
import unittest
import os
import sys
import io
import json
from unittest.mock import MagicMock, patch

# Add deploy folder to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app_utils import analyze_single_file_content, generate_quote, slicer_volume_adjustment
from ai import PrintAnalysis

class TestAppLogic(unittest.TestCase):
    
    def test_volume_adjustment(self):
        # 100cm3, 20% infill, 25% walls
        # wall_vol = 25
        # infill_vol = 100 * (0.75) * 0.20 = 15
        # total = 40
        vol = slicer_volume_adjustment(100, 20, 25)
        self.assertAlmostEqual(vol, 40.0)
        
    def test_quote_generation(self):
        # Material 100, Time 1h, Machine 30, Elec 12, Labor 50 -> Base = 192
        # Profit 50% -> 192 + 96 = 288
        # GST 18% -> 288 * 0.18 = 51.84
        # Total = 339.84
        q = generate_quote(100, 1, 30, 12, 50, 0.50, 0.18, 0)
        self.assertAlmostEqual(q['Final Price (₹)'], 339.84)
        
    def test_quote_with_delivery(self):
        # Same as above + 100 Delivery
        # Total = 439.84
        q = generate_quote(100, 1, 30, 12, 50, 0.50, 0.18, 100)
        self.assertAlmostEqual(q['Final Price (₹)'], 439.84)
        self.assertEqual(q['Delivery (₹)'], 100)

    def test_ai_schema(self):
        # Validate that the Pydantic model accepts valid data
        valid_data = {
            "verdict": "GO",
            "risk_level": "Low",
            "summary": "Looks good.",
            "warnings": [],
            "settings": ["200C"],
            "tags": ["#PLA"]
        }
        obj = PrintAnalysis(**valid_data)
        self.assertEqual(obj.verdict, "GO")

    @patch('app_utils.trimesh.load')
    def test_analyze_file(self, mock_load):
        # Mock trimesh volume
        mock_mesh = MagicMock()
        mock_mesh.is_empty = False
        mock_mesh.volume = 10000.0 # 10 cm3
        mock_mesh.vertices = [1, 2, 3]
        mock_load.return_value = mock_mesh
        
        dummy_file = b"fake_stl_data"
        res = analyze_single_file_content(dummy_file, "test.stl")
        
        self.assertEqual(res['Raw Volume (cm3)'], 10.0)
        self.assertNotIn('error', res)

if __name__ == '__main__':
    unittest.main()
