import io
import textwrap
import trimesh
import pandas as pd
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

def export_pdf_report(data, image_urls=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    def draw_wrapped_text(c, text, x, y, max_width, line_height=14):
        lines = []
        if text is None: text = ""
        text = str(text)
        for paragraph in text.split('\n'):
            wrapped = textwrap.wrap(paragraph, width=90) 
            if not wrapped: lines.append("")
            lines.extend(wrapped)
        for line in lines:
            if y < 50:
                c.showPage()
                y = height - 50
            c.drawString(x, y, line)
            y -= line_height
        return y

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, "3D Model Forensic Report")
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 20
    c.line(50, y, width - 50, y)
    y -= 30

    if image_urls:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Visual Evidence:")
        y -= 110
        x_offset = 50
        for img_url in image_urls[:3]:
            try:
                response = requests.get(img_url, timeout=1)
                if response.status_code == 200:
                    img_data = io.BytesIO(response.content)
                    img = ImageReader(img_data)
                    c.drawImage(img, x_offset, y, width=100, height=100, preserveAspectRatio=True)
                    x_offset += 110
            except: pass
        y -= 20

    c.setFont("Helvetica", 11)
    if isinstance(data, dict):
        for key, value in data.items():
            if "AI" in key or "Details" in key:
                c.setFont("Helvetica-Bold", 12)
                y = draw_wrapped_text(c, f"{key}:", 50, y, 500)
                y -= 5
                c.setFont("Helvetica", 11)
                y = draw_wrapped_text(c, str(value), 50, y, 500)
                y -= 15
            elif "Images" in key: continue 
            else:
                c.drawString(50, y, f"{key}: {value}")
                y -= 20
    c.save()
    buffer.seek(0)
    return buffer

# --- MATH HELPERS ---
def slicer_volume_adjustment(mesh_volume_cm3, infill_percent=20, wall_percent=25):
    wall_fraction = wall_percent / 100
    infill_fraction = infill_percent / 100
    effective_volume = (mesh_volume_cm3 * wall_fraction) + (mesh_volume_cm3 * (1 - wall_fraction) * infill_fraction)
    return effective_volume

def estimate_print_time(effective_volume_cm3, layer_height=0.2, printer_speed_mm_s=60, nozzle_mm=0.4):
    extrusion_rate = printer_speed_mm_s * layer_height * nozzle_mm
    total_mm3 = effective_volume_cm3 * 1000
    if extrusion_rate == 0: return 0
    return round((total_mm3 / extrusion_rate) / 3600, 2)

def analyze_single_file_content(file_content, file_name):
    """
    HEAVY FUNCTION: Runs only once per file.
    Calculates raw geometry only.
    """
    try:
        # Load from RAM directly
        file_obj = io.BytesIO(file_content)
        mesh = trimesh.load(file_obj, file_type='stl', force="mesh")
        
        if mesh.is_empty: raise ValueError("Empty mesh")
        
        volume_cm3 = mesh.volume / 1000.0
        
        return {
            "File Name": file_name,
            "Raw Volume (cm3)": round(volume_cm3, 2),
            "Vertices": len(mesh.vertices)
        }
    except Exception as e:
        return {"error": str(e), "File Name": file_name}

def generate_quote(material_cost, print_time_hr, machine_rate_per_hr, electricity_per_hr, labour_rate_per_hr, profit_margin, gst, delivery_cost=0):
    base_cost = material_cost + (print_time_hr * machine_rate_per_hr) + (print_time_hr * electricity_per_hr) + (print_time_hr * labour_rate_per_hr)
    profit = base_cost * profit_margin
    subtotal = base_cost + profit
    gst_amount = subtotal * gst
    total = subtotal + gst_amount + delivery_cost
    return {
        "Material Cost (₹)": round(material_cost, 2),
        "Machine Cost (₹)": round(print_time_hr * machine_rate_per_hr, 2),
        "Electricity (₹)": round(print_time_hr * electricity_per_hr, 2),
        "Labour Cost (₹)": round(print_time_hr * labour_rate_per_hr, 2),
        "Profit (₹)": round(profit, 2),
        "GST (₹)": round(gst_amount, 2),
        "Delivery (₹)": round(delivery_cost, 2),
        "Final Price (₹)": round(total, 2)
    }
