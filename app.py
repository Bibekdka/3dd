import asyncio
import sys
import textwrap

# Fix for Windows asyncio loop policy
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import streamlit as st
import trimesh
import os
import tempfile
import pandas as pd
import json
import io
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import requests

from scraper import scrape_model_page, clean_scraped_text
from ai import ai_analyze
from history import load_history, add_history_entry, update_print_status

load_dotenv()

# --- DEFAULT CONFIGURATION ---
DEFAULT_PRINTERS = {
    "Ender 3 / Ender 3 V2": {"max_speed_mm_s": 50, "nozzle_mm": 0.4, "max_build_mm": (220, 220, 250), "reliability": 0.75},
    "Prusa MK3 / MK4": {"max_speed_mm_s": 70, "nozzle_mm": 0.4, "max_build_mm": (250, 210, 210), "reliability": 0.90},
    "Bambu Lab X1 / P1": {"max_speed_mm_s": 120, "nozzle_mm": 0.4, "max_build_mm": (256, 256, 256), "reliability": 0.95},
    "Anycubic Kobra 2 Neo": {"max_speed_mm_s": 150, "nozzle_mm": 0.4, "max_build_mm": (220, 220, 250), "reliability": 0.85}
}

# --- PDF HELPERS ---
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

    # PDF Content
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
        c.drawString(50, y, "Visual Evidence (User Makes):")
        y -= 110
        x_offset = 50
        for img_url in image_urls[:3]:
            try:
                response = requests.get(img_url, timeout=3, stream=True)
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
            if key == "Verdict":
                c.setFont("Helvetica-Bold", 14)
                val_str = str(value).lower()
                if any(x in val_str for x in ["go", "easy", "safe"]): c.setFillColor(colors.green)
                elif any(x in val_str for x in ["stop", "hard", "fail"]): c.setFillColor(colors.red)
                else: c.setFillColor(colors.black)
                c.drawString(50, y, f"{key}: {value}")
                c.setFillColor(colors.black)
                y -= 25
                c.setFont("Helvetica", 11)
            elif "AI" in key or "Details" in key:
                c.setFont("Helvetica-Bold", 12)
                y = draw_wrapped_text(c, f"{key}:", 50, y, 500)
                y -= 5
                c.setFont("Helvetica", 11)
                y = draw_wrapped_text(c, str(value), 50, y, 500)
                y -= 15
            elif "Images" in key:
                continue 
            else:
                c.drawString(50, y, f"{key}: {value}")
                y -= 20
    else:
        y = draw_wrapped_text(c, str(data), 50, y, 500)
                
    c.save()
    buffer.seek(0)
    return buffer

# --- ANALYTICS HELPERS ---
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

@st.cache_data(show_spinner=False)
def analyze_single_file_content(file_content, file_name, density, cost_per_kg, infill, walls, speed_mm_s, nozzle_mm):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mesh = trimesh.load(tmp_path, force="mesh")
        try: os.remove(tmp_path)
        except: pass

        if mesh.is_empty: raise ValueError("Empty mesh")
        
        volume_cm3 = mesh.volume / 1000.0
        effective_vol = slicer_volume_adjustment(volume_cm3, infill, walls)
        weight_g = effective_vol * density
        cost = (weight_g / 1000) * cost_per_kg
        time_hr = estimate_print_time(effective_vol, 0.2, speed_mm_s, nozzle_mm)
        
        return {
            "File Name": file_name,
            "Effective Volume (cm3)": round(effective_vol, 2),
            "Weight (g)": round(weight_g, 2),
            "Cost (₹)": round(cost, 2),
            "Print Time (hr)": time_hr
        }
    except Exception as e:
        return {"error": str(e), "File Name": file_name}

def generate_quote(material_cost, print_time_hr, machine_rate_per_hr, electricity_per_hr, labour_rate_per_hr, profit_margin, gst):
    base_cost = material_cost + (print_time_hr * machine_rate_per_hr) + (print_time_hr * electricity_per_hr) + (print_time_hr * labour_rate_per_hr)
    profit = base_cost * profit_margin
    subtotal = base_cost + profit
    gst_amount = subtotal * gst
    total = subtotal + gst_amount
    return {
        "Material Cost (₹)": round(material_cost, 2),
        "Machine Cost (₹)": round(print_time_hr * machine_rate_per_hr, 2),
        "Electricity (₹)": round(print_time_hr * electricity_per_hr, 2),
        "Labour Cost (₹)": round(print_time_hr * labour_rate_per_hr, 2),
        "Profit (₹)": round(profit, 2),
        "GST (₹)": round(gst_amount, 2),
        "Final Price (₹)": round(total, 2)
    }

def main():
    st.set_page_config(page_title="3D Deep Dive Analyst", page_icon="🕵️", layout="wide")
    
    # --- DYNAMIC CONFIGURATION ---
    if "printers" not in st.session_state:
        st.session_state["printers"] = DEFAULT_PRINTERS.copy()
    if "quantities" not in st.session_state: st.session_state["quantities"] = {}
    if "analyzed_files" not in st.session_state: st.session_state["analyzed_files"] = {}

    st.title("🕵️ 3D Deep Dive Analyst")
    
    with st.sidebar:
        st.header("⚙️ Configuration")
        if os.getenv("GEMINI_API_KEY"): 
             st.success("AI Active", icon="✅")
        else:
             st.warning("AI Key Missing", icon="⚠️")
        
        # Printer Selection
        printer_names = list(st.session_state["printers"].keys())
        selected_printer_name = st.selectbox("Current Printer", printer_names)
        current_printer = st.session_state["printers"][selected_printer_name]
        
        # Edit Printer
        with st.expander("🛠 Edit Printer Profile"):
            new_speed = st.number_input("Speed (mm/s)", value=current_printer["max_speed_mm_s"])
            new_nozzle = st.number_input("Nozzle (mm)", value=current_printer["nozzle_mm"])
            if st.button("Update Profile"):
                st.session_state["printers"][selected_printer_name]["max_speed_mm_s"] = new_speed
                st.session_state["printers"][selected_printer_name]["nozzle_mm"] = new_nozzle
                st.success("Updated!")
                st.rerun()

        st.divider()
        debug_mode = st.checkbox("🐞 Debug Mode")
        
        # Queue Summary
        queue_df = load_history()
        if not queue_df.empty and "PrintStatus" in queue_df.columns:
            print_items = queue_df[queue_df["PrintStatus"] == "Print"]
            st.metric("Print Queue Value", f"₹{print_items['Cost_INR'].sum():,.0f}", f"{len(print_items)} items")

    tab_scrape, tab_est, tab_hist = st.tabs(["🖼️ Deep Analysis", "🚀 Calculator", "📜 History"])

    # --- 1. DEEP ANALYSIS TAB ---
    with tab_scrape:
        st.info("💡 Paste a MakerWorld/Printables link to analyze failure points and see real user makes.")
        c1, c2 = st.columns([3, 1])
        with c1:
            url = st.text_input("Model URL", placeholder="https://makerworld.com/en/models/...")
        with c2:
            st.write("") # Spacer
            st.write("")
            analyze_btn = st.button("🚀 Analyze", type="primary", use_container_width=True)

        if analyze_btn and url:
            with st.status("🕵️ Investigating...", expanded=True) as status:
                st.write("1. Launching visual scraper...")
                data = scrape_model_page(url, debug=debug_mode)
                
                if "error" in data:
                    status.update(label="Failed", state="error")
                    st.error(data["error"])
                    if debug_mode: st.json(data.get("debug"))
                    st.stop()
                
                st.write(f"2. Found {len(data['images'])} images and extracted {len(data['text'])} chars.")
                
                st.write("3. AI analyzing 'Vibe' & 'Reality'...")
                prompt = f"""
                Act as a 3D Printing Forensic Expert.
                
                RAW TEXT: {data['text']}
                
                TASK:
                1. **Reality Check**: Compare User Comments vs Description.
                2. **Vibe Check**: Classify: [Easy/Frustrating/Technical]. Use emojis.
                3. **Hardware**: specific nozzles, plates, or glues mentioned?
                4. **Filament**: Brands/Colors/Types?
                5. **Failures**: Spaghetti, warping, etc?
                
                OUTPUT FORMAT:
                **Summary**: ...
                **The Vibe**: ...
                **Reality vs Renders**: ...
                **Hardware/Filament**: ...
                **Failure Modes**: ...
                **Verdict**: [GO / CAUTION / STOP]
                """
                ai_result = ai_analyze(prompt)
                
                st.session_state['vis_result'] = ai_result
                st.session_state['vis_images'] = data['images']
                st.session_state['vis_url'] = url
                status.update(label="Complete!", state="complete", expanded=False)

        # Result Display
        if 'vis_result' in st.session_state:
            res = st.session_state['vis_result']
            imgs = st.session_state['vis_images']
            
            st.subheader("📸 Visual Proof")
            st.caption("These images are pulled from key user interactions (Makes/Comments) to show reality.")
            if imgs:
                cols = st.columns(4)
                for i, img in enumerate(imgs[:8]):
                    with cols[i % 4]:
                        st.image(img, use_container_width=True)
            else:
                st.warning("No user images found.")
            
            st.divider()
            
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader("🧠 Report")
                st.markdown(res['details'])
            with c2:
                st.subheader("Action")
                pdf_payload = {"Model": st.session_state.get('vis_url'), "Details": res['details'], "Verdict": "GO" if "GO" in res['details'] else "STOP"}
                pdf_data = export_pdf_report(pdf_payload, image_urls=imgs)
                st.download_button("📥 PDF Report", pdf_data, "Report.pdf", "application/pdf", use_container_width=True)

    # --- 2. CALCULATOR TAB ---
    with tab_est:
        st.markdown("### 📦 Batch Estimator")
        
        with st.expander("⚙️ Estimation Settings", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                infill = st.slider("Infill %", 0, 100, 20)
                walls = st.slider("Walls %", 0, 100, 25)
            with col2:
                density = st.number_input("Material Density (g/cm³)", value=1.24)
                cost_kg = st.number_input("Filament Cost (₹/kg)", value=1200.0)
            with col3:
                machine_rate = st.number_input("Machine Rate (₹/hr)", value=50)
                profit_pct = st.number_input("Profit Margin (%)", value=30)
                elec_rate = st.number_input("Electricity (₹/hr)", value=10)
                labour_rate = st.number_input("Labour (₹/hr)", value=50)
                gst_pct = st.number_input("GST %", value=0)

        uploaded_stls = st.file_uploader("Upload multiple STL files", type=["stl"], accept_multiple_files=True)
        batch_results = []
        
        if uploaded_stls:
            # 1. Update Quantities
            current_names = [f.name for f in uploaded_stls]
            st.session_state["quantities"] = {k: v for k, v in st.session_state["quantities"].items() if k in current_names}
            
            with st.status("Processing files...", expanded=True) as status:
                for stl in uploaded_stls:
                    if stl.name not in st.session_state["quantities"]:
                        st.session_state["quantities"][stl.name] = 1
                    
                    if stl.name in st.session_state["analyzed_files"]:
                        batch_results.append(st.session_state["analyzed_files"][stl.name])
                    else:
                        st.write(f"Analyzing {stl.name}...")
                        stl.seek(0)
                        bytes_data = stl.read()
                        analysis = analyze_single_file_content(
                            bytes_data, stl.name, density, cost_kg, infill, walls,
                            current_printer["max_speed_mm_s"], current_printer["nozzle_mm"]
                        )
                        if "error" not in analysis:
                            st.session_state["analyzed_files"][stl.name] = analysis
                            batch_results.append(analysis)
                status.update(label="Analysis Ready", state="complete", expanded=False)

        if batch_results:
             st.subheader("📦 Batch Analysis")
             total_cost_inr = 0
             total_time = 0
             
             for idx, item in enumerate(batch_results):
                 name = item["File Name"]
                 qty = st.session_state["quantities"].get(name, 1)
                 
                 item_cost = item["Cost (₹)"] * qty
                 item_time = item["Print Time (hr)"] * qty
                 
                 total_cost_inr += item_cost
                 total_time += item_time

                 with st.container():
                     c1, c2, c3, c4 = st.columns([3, 1, 1, 2])
                     c1.write(f"**{name}**")
                     c1.caption(f"{item['Effective Volume (cm3)']} cm³ | {item['Print Time (hr)']} hr")
                     if c2.button("➖", key=f"d_{idx}") and qty > 1:
                         st.session_state["quantities"][name] -= 1
                         st.rerun()
                     c3.write(f"Qty: {qty}")
                     if c4.button("➕", key=f"i_{idx}"):
                         st.session_state["quantities"][name] += 1
                         st.rerun()
                     st.divider()
            
             # Generate Quote
             quote = generate_quote(total_cost_inr, total_time, machine_rate, elec_rate, labour_rate, profit_pct/100, gst_pct/100)
             st.info(f"Final Quote: ₹{quote['Final Price (₹)']}")
             with st.expander("Cost Breakdown"):
                 st.table(pd.DataFrame(quote.items(), columns=["Item", "Value"]))
            
             if st.button("💾 Save Batch to History"):
                 entry_name = f"Batch ({len(batch_results)} files)" if len(batch_results) > 1 else batch_results[0]["File Name"]
                 add_history_entry("Batch Estimate", entry_name, f"Cost: ₹{quote['Final Price (₹)']}", quote['Final Price (₹)'])
                 st.success("Saved!")

    # --- 3. HISTORY TAB ---
    with tab_hist:
        st.subheader("📜 Management")
        history_df = load_history()
        st.dataframe(history_df, use_container_width=True)
        if st.button("🗑️ Clear All History"):
             if os.path.exists("history.csv"): os.remove("history.csv")
             st.rerun()

    # --- DEBUG SECTION ---
    if debug_mode:
        with st.expander("🛠 Developer Tools (Debug Mode)", expanded=True):
            st.write("Session State:")
            st.write(st.session_state)
            if st.button("Clear Cache"):
                st.cache_data.clear()
                st.rerun()

if __name__ == "__main__":
    main()
