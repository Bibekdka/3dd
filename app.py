import asyncio
import sys
import textwrap

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
from reportlab.lib.utils import ImageReader  # For embedding images
import requests

from scraper import scrape_model_page, clean_scraped_text
from ai import ai_analyze
from history import load_history, add_history_entry, update_print_status

load_dotenv()

# --- PRINTER PROFILES ---
PRINTER_PROFILES = {
    "Ender 3 / Ender 3 V2": {"max_speed_mm_s": 50, "nozzle_mm": 0.4, "max_build_mm": (220, 220, 250), "reliability": 0.75},
    "Prusa MK3 / MK4": {"max_speed_mm_s": 70, "nozzle_mm": 0.4, "max_build_mm": (250, 210, 210), "reliability": 0.90},
    "Bambu Lab X1 / P1": {"max_speed_mm_s": 120, "nozzle_mm": 0.4, "max_build_mm": (256, 256, 256), "reliability": 0.95},
    "Anycubic Kobra 2 Neo": {"max_speed_mm_s": 150, "nozzle_mm": 0.4, "max_build_mm": (220, 220, 250), "reliability": 0.85}
}

# --- CALCULATOR HELPERS ---
def download_file(url):
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        return io.BytesIO(response.content)
    except Exception:
        return None

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
    tmp_path = None
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
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass

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

# --- 4. ADVANCED PDF FORMATTING (Images + Color) ---
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

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, "3D Model Forensic Report")
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 20
    c.line(50, y, width - 50, y)
    y -= 30

    # --- EMBEDDING IMAGES ---
    if image_urls:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Visual Evidence (User Makes):")
        y -= 110 # Space for images
        
        x_offset = 50
        # Try to embed first 3 images
        for img_url in image_urls[:3]:
            try:
                # Basic check to avoid huge downloads or timeouts
                response = requests.get(img_url, timeout=3, stream=True)
                if response.status_code == 200:
                    img_data = io.BytesIO(response.content)
                    img = ImageReader(img_data)
                    # Draw image thumbnail (100x100)
                    c.drawImage(img, x_offset, y, width=100, height=100, preserveAspectRatio=True)
                    x_offset += 110
            except:
                pass # Skip broken images
        y -= 20

    c.setFont("Helvetica", 11)
    
    if isinstance(data, dict):
        for key, value in data.items():
            # 4. COLOR CODED VERDICT
            if key == "Verdict":
                c.setFont("Helvetica-Bold", 14)
                val_str = str(value).lower()
                if "go" in val_str or "easy" in val_str or "safe" in val_str:
                    c.setFillColor(colors.green)
                elif "stop" in val_str or "hard" in val_str or "fail" in val_str:
                    c.setFillColor(colors.red)
                else:
                    c.setFillColor(colors.black)
                
                c.drawString(50, y, f"{key}: {value}")
                c.setFillColor(colors.black) # Reset
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

def main():
    st.set_page_config(page_title="3D Deep Dive Analyst", page_icon="🕵️", layout="wide")
    SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

    st.title("🕵️ 3D Deep Dive Analyst")
    
    with st.sidebar:
        if os.getenv("GEMINI_API_KEY"): st.success("AI Connected", icon="✅")
        else: st.warning("AI Key Missing", icon="⚠️")
        debug_mode = st.sidebar.checkbox("🛠 Debug Scraper")
        st.subheader("🖨️ Printer Profile")
        printer_name = st.sidebar.selectbox("Select Printer", list(PRINTER_PROFILES.keys()))
        printer = PRINTER_PROFILES[printer_name]

        # --- PRINT QUEUE SIDEBAR OVERVIEW ---
        st.divider()
        st.subheader("📋 Print Queue")
        queue_df = load_history()
        if not queue_df.empty and "PrintStatus" in queue_df.columns:
            print_items = queue_df[queue_df["PrintStatus"] == "Print"]
            if not print_items.empty:
                total_q_cost = print_items["Cost_INR"].sum()
                st.caption(f"Total: ₹{total_q_cost:,.0f} | {len(print_items)} Items")
                for _, row in print_items.iterrows():
                    with st.expander(f"📌 {row['Name'][:20]}...", expanded=False):
                        st.write(f"₹{row['Cost_INR']:.2f}")
            else:
                 st.caption("Queue empty.")

    tab_scrape, tab_est, tab_hist = st.tabs(["🖼️ Deep Analysis", "🚀 Calculator", "📜 History"])

    with tab_scrape:
        st.markdown("### 🔍 Model Forensic Report")
        st.markdown("Enter a URL. We will find **Filament Choices**, **Failure Modes**, and **Embed Images** in your report.")
        
        url = st.text_input("Model URL", placeholder="https://...")
        
        if st.button("🚀 Analyze Everything", type="primary"):
            if not url: st.stop()
            
            with st.status("🕵️ deep diving...", expanded=True) as status:
                st.write("1. Launching visual scraper (Hunting 'Makes' tab)...")
                data = scrape_model_page(url, debug=debug_mode)
                
                if "error" in data:
                    status.update(label="Failed", state="error")
                    st.error(data["error"])
                    if debug_mode: st.write(data.get("debug"))
                    st.stop()
                
                st.write(f"2. Found {len(data['images'])} visual proofs.")
                
                # --- 3. SENTIMENT & VIBE ANALYSIS PROMPT ---
                st.write("3. AI determining 'Vibe' & 'Reality'...")
                prompt = f"""
                Act as a 3D Printing Forensic Expert. Analyze this scraped data.
                
                RAW TEXT:
                {data['text']}
                
                TASK:
                1. **Reality Check**: Compare the User Comments to the Description. Does "User Reality" match "Official Renders"?
                2. **Vibe Check**: Classify the print experience:
                   - **Easy**: ("Printed first try", "Kids loved it")
                   - **Frustrating**: ("Nightmare supports", "Failed 3 times")
                   - **Technical**: ("Needs precise cooling", "Calibrate flow first")
                3. **Hardware & Filament**: List SPECIFIC filaments (Silk, Matte, TPU) and Hardware (0.6 nozzle, PEI) mentioned.
                4. **Failure Modes**: What SPECIFICALLY goes wrong? (Spaghetti, Clogging, Adhesion).
                
                OUTPUT FORMAT (Markdown):
                **Summary**: [1 sentence]
                **The Vibe**: [Easy / Frustrating / Technical] - [Explanation]
                **Reality vs Renders**: [Honest comparison]
                **Hardware/Filament Needs**: [List]
                **Failure Modes**: [List]
                **Verdict**: [GO (Green) / CAUTION (Yellow) / STOP (Red)]
                """
                
                ai_result = ai_analyze(prompt)
                
                st.session_state['vis_result'] = ai_result
                st.session_state['vis_images'] = data['images']
                st.session_state['vis_url'] = url
                
                status.update(label="Investigation Complete!", state="complete", expanded=False)

        # --- RESULTS DISPLAY ---
        if 'vis_result' in st.session_state:
            res = st.session_state['vis_result']
            imgs = st.session_state['vis_images']
            
            # 1. VISUAL EVIDENCE
            st.subheader("📸 Visual Evidence")
            if imgs:
                st.caption("These images are pulled from User Makes to show *real* quality.")
                cols = st.columns(5)
                for idx, img in enumerate(imgs[:10]): 
                    with cols[idx % 5]:
                        st.image(img, use_container_width=True)
            
            st.divider()

            # 2. INTELLIGENCE REPORT
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader("🧠 Forensic Report")
                st.markdown(res['details'])
                
            with c2:
                st.subheader("💾 Export Forensic Report")
                
                # Prepare PDF Payload
                pdf_payload = {
                    "Model": st.session_state.get('vis_url', 'Unknown'),
                    "AI Summary": res['summary'],
                    "AI Details": res['details'],
                    "Verdict": "GO" if "GO" in res['details'] or "Green" in res['details'] else "CAUTION" # Simple extractor
                }
                
                # Pass images to PDF generator
                pdf_data = export_pdf_report(pdf_payload, image_urls=imgs)
                
                st.download_button("📥 Download Report (w/ Images)", pdf_data, "Forensic_Report.pdf", "application/pdf")
                st.caption("PDF includes embedded images and color-coded verdict.")

    # --- CALCULATOR TAB ---
    with tab_est:
        st.markdown("### Manual STL Upload & Estimator")
        
        col1, col2 = st.columns(2)
        with col1:
             st.subheader("Slicer Settings")
             infill = st.slider("Infill %", 0, 100, 20)
             walls = st.slider("Walls %", 0, 100, 25)
        with col2:
             st.subheader("Material Settings")
             density = st.number_input("Density (g/cm3)", value=1.24)
             cost_kg = st.number_input("Cost/kg (₹)", value=1200.0)

        # Initialize Session State for Calc
        if "quantities" not in st.session_state: st.session_state["quantities"] = {}
        if "analyzed_files" not in st.session_state: st.session_state["analyzed_files"] = {}

        uploaded_stls = st.file_uploader("Upload multiple STL files", type=["stl"], accept_multiple_files=True)
        batch_results = []

        if uploaded_stls:
            # 1. Update Quantities Dictionary
            current_names = [f.name for f in uploaded_stls]
            st.session_state["quantities"] = {k: v for k, v in st.session_state["quantities"].items() if k in current_names}
            
            # 2. Check settings change to clear cache
            settings_key = f"{infill}_{walls}_{density}_{cost_kg}_{printer_name}"
            if "last_settings" not in st.session_state or st.session_state["last_settings"] != settings_key:
                 st.session_state["analyzed_files"] = {}
                 st.session_state["last_settings"] = settings_key

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
                            printer["max_speed_mm_s"], printer["nozzle_mm"]
                        )
                        if "error" not in analysis:
                            st.session_state["analyzed_files"][stl.name] = analysis
                            batch_results.append(analysis)
                status.update(label="Analysis Ready", state="complete", expanded=False)

        # Display Results
        if batch_results:
             st.subheader("📦 Batch Analysis")
             total_cost_inr = 0
             total_weight = 0
             total_time = 0
             
             for idx, item in enumerate(batch_results):
                 name = item["File Name"]
                 qty = st.session_state["quantities"].get(name, 1)
                 
                 item_cost = item["Cost (₹)"] * qty
                 item_weight = item["Weight (g)"] * qty
                 item_time = item["Print Time (hr)"] * qty
                 
                 total_cost_inr += item_cost
                 total_weight += item_weight
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

             c1, c2, c3 = st.columns(3)
             c1.metric("Total Cost", f"₹{total_cost_inr:,.0f}")
             c2.metric("Total Weight", f"{total_weight:.1f} g")
             c3.metric("Total Time", f"{total_time:.1f} hr")

             # Quote Generation
             st.subheader("💰 Quotation Tool")
             cq1, cq2 = st.columns(2)
             with cq1:
                 machine_rate = st.number_input("Machine Rate (₹/hr)", value=50)
                 elec_rate = st.number_input("Electricity (₹/hr)", value=10)
             with cq2:
                 profit_pct = st.number_input("Profit %", value=30)
                 labour_rate = st.number_input("Labour (₹/hr)", value=50)
             gst_pct = st.number_input("GST %", value=0)

             quote = generate_quote(total_cost_inr, total_time, machine_rate, elec_rate, labour_rate, profit_pct/100, gst_pct/100)
             st.table(pd.DataFrame(quote.items(), columns=["Item", "Value"]))

             # Save History Button
             if st.button("💾 Save Batch to History"):
                 entry_name = f"Batch ({len(batch_results)} files)" if len(batch_results) > 1 else batch_results[0]["File Name"]
                 add_history_entry(
                     "Batch Estimate", 
                     entry_name, 
                     f"Cost: ₹{quote['Final Price (₹)']}", 
                     quote['Final Price (₹)']
                 )
                 st.success("Saved to History!")

    with tab_hist:
         history_df = load_history()
         st.dataframe(history_df)

if __name__ == "__main__":
    main()
