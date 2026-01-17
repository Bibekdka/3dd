import asyncio
import sys

# Fix for Windows + Streamlit + Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import streamlit as st
import trimesh
import os
import tempfile
import pandas as pd
import json
import io  # ADDED: To handle PDF in memory
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Import from new modules
from scraper import scrape_model_page, clean_scraped_text
from ai import ai_analyze
from history import load_history, add_history_entry, update_print_status

# Load environment variables
load_dotenv()

PRINTER_PROFILES = {
    "Ender 3 / Ender 3 V2": {
        "max_speed_mm_s": 50,
        "nozzle_mm": 0.4,
        "max_build_mm": (220, 220, 250),
        "reliability": 0.75
    },
    "Prusa MK3 / MK4": {
        "max_speed_mm_s": 70,
        "nozzle_mm": 0.4,
        "max_build_mm": (250, 210, 210),
        "reliability": 0.90
    },
    "Bambu Lab X1 / P1": {
        "max_speed_mm_s": 120,
        "nozzle_mm": 0.4,
        "max_build_mm": (256, 256, 256),
        "reliability": 0.95
    },
    "Anycubic Kobra 2 Neo": {
        "max_speed_mm_s": 150,
        "nozzle_mm": 0.4,
        "max_build_mm": (220, 220, 250),
        "reliability": 0.85
    }
}

# --- IMPROVEMENT: Generate PDF to memory (BytesIO) instead of disk ---
def export_pdf_report(data):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 800

    c.setFont("Helvetica", 14)
    c.drawString(40, 820, "3D Slicer Volume Estimator Report")
    
    c.setFont("Helvetica", 11)

    if isinstance(data, dict):
        for key, value in data.items():
            c.drawString(40, y, f"{key}: {value}")
            y -= 25
            if y < 50:
                c.showPage()
                y = 800
    else:
        text_lines = str(data).split('\n')
        for line in text_lines:
            c.drawString(40, y, line)
            y -= 20
            if y < 50:
                c.showPage()
                y = 800

    c.save()
    buffer.seek(0)
    return buffer

def display_ai_section(prompt_text, button_label="Generate AI Assessment"):
    if st.button(button_label):
        with st.spinner("Consulting Gemini..."):
            ai_result = ai_analyze(prompt_text)

        st.subheader("🧠 AI Recommendations")
        st.markdown(f"**Summary:** {ai_result['summary']}")
        st.markdown(ai_result["details"])

def slicer_volume_adjustment(mesh_volume_cm3, infill_percent=20, wall_percent=25):
    wall_fraction = wall_percent / 100
    infill_fraction = infill_percent / 100
    wall_volume = mesh_volume_cm3 * wall_fraction
    internal_volume = mesh_volume_cm3 * (1 - wall_fraction)
    effective_volume = wall_volume + (internal_volume * infill_fraction)
    return effective_volume

def estimate_print_time(effective_volume_cm3, layer_height=0.2, printer_speed_mm_s=60, nozzle_mm=0.4):
    extrusion_rate = printer_speed_mm_s * layer_height * nozzle_mm
    total_mm3 = effective_volume_cm3 * 1000
    seconds = total_mm3 / extrusion_rate
    hours = seconds / 3600
    return round(hours, 2)

# --- IMPROVEMENT: Caching this function improves performance ---
@st.cache_data(show_spinner=False)
def analyze_single_file_content(file_content, file_name, density, cost_per_kg, infill, walls, speed_mm_s, nozzle_mm):
    """
    Separated logic to allow Streamlit caching. 
    Accepts bytes (file_content) instead of file path to work with cache.
    """
    tmp_path = None
    try:
        # Create temp file just for trimesh with Explicit cleanup handling
        with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        mesh = trimesh.load(tmp_path, force="mesh")
        
        # Clean up immediately after loading
        try:
             os.remove(tmp_path)
             tmp_path = None 
        except:
             pass

        if mesh.is_empty:
            raise ValueError("Empty or invalid STL mesh")
        
        volume_raw = mesh.volume
        volume_cm3 = volume_raw / 1000.0
        
        effective_volume = slicer_volume_adjustment(volume_cm3, infill_percent=infill, wall_percent=walls)
        weight_g = effective_volume * density
        cost = (weight_g / 1000) * cost_per_kg
        
        print_time = estimate_print_time(effective_volume, printer_speed_mm_s=speed_mm_s, nozzle_mm=nozzle_mm)
        
        return {
            "File Name": file_name,
            "Raw Volume (cm3)": round(volume_cm3, 2),
            "Effective Volume (cm3)": round(effective_volume, 2),
            "Weight (g)": round(weight_g, 2),
            "Cost (₹)": round(cost, 2),
            "Print Time (hr)": print_time,
            "Vertices": len(mesh.vertices),
            "Faces": len(mesh.faces),
            "Watertight": mesh.is_watertight
        }
    except Exception as e:
        return {"error": str(e), "File Name": file_name}
    finally:
        # Double check cleanup
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

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
    st.set_page_config(page_title="3D Slicer Volume Estimator", page_icon="🧊")
    SAFE_MODE = os.getenv("STREAMLIT_SAFE_MODE", "false").lower() == "true"

    st.title("🧊 3D Slicer Volume Estimator")
    
    with st.sidebar:
        if os.getenv("GEMINI_API_KEY"):
            st.success("Gemini API Key Detected", icon="✅")
        else:
            st.warning("Gemini API Key Missing", icon="⚠️")
        
        st.divider()
        debug_mode = st.sidebar.checkbox("🛠 Scraper Debug Mode")
        st.subheader("🖨️ Printer Profile")
        printer_name = st.sidebar.selectbox("Select Printer", list(PRINTER_PROFILES.keys()))
        printer = PRINTER_PROFILES[printer_name]
        
        # --- PRINT QUEUE SECTION ---
        st.divider()
        st.subheader("📋 Print Queue")
        queue_df = load_history()
        if not queue_df.empty and "PrintStatus" in queue_df.columns:
            # Filter for items marked as "Print"
            print_items = queue_df[queue_df["PrintStatus"] == "Print"]
            
            if not print_items.empty:
                # Calculate totals
                total_q_cost = print_items["Cost_INR"].sum()
                st.caption(f"Total: ₹{total_q_cost:,.0f} | {len(print_items)} Items")
                
                for _, row in print_items.iterrows():
                    with st.expander(f"📌 {row['Name']}", expanded=False):
                        st.markdown(f"**Details:** {row['Details']}")
                        if row.get("Cost_INR", 0) > 0:
                            st.markdown(f"**Cost:** ₹{row['Cost_INR']:.2f}")
                        if row.get("Type") == "Link Scraper":
                             st.markdown(f"[View Source]({row['Name']})")
            else:
                st.info("Queue empty. Mark items as 'Print' in History.")


    st.markdown("Upload STL files to calculate volume and estimate effective cost/weight.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Slicer Settings")
        infill = st.slider("Infill Percentage (%)", 0, 100, 20)
        walls = st.slider("Wall/Shell Percentage (%)", 0, 100, 25)
    
    with col2:
        st.subheader("Material Settings")
        density = st.number_input("Material Density (g/cm3)", value=1.24)
        cost_per_kg = st.number_input("Cost per kg (₹)", value=1200.0)

    # Initialize Session State
    if "quantities" not in st.session_state:
        st.session_state["quantities"] = {}
    if "analyzed_files" not in st.session_state:
        st.session_state["analyzed_files"] = {}

    tab_estimator, tab_history = st.tabs(["🚀 Estimator", "📜 History"])

    with tab_estimator:
        uploaded_stls = st.file_uploader("Upload multiple STL files", type=["stl"], accept_multiple_files=True)

        batch_results = []
        
        if uploaded_stls:
            # 1. Update Quantities Dictionary
            current_names = [f.name for f in uploaded_stls]
            
            # Remove deleted files from memory
            st.session_state["quantities"] = {k: v for k, v in st.session_state["quantities"].items() if k in current_names}
            st.session_state["analyzed_files"] = {k: v for k, v in st.session_state["analyzed_files"].items() if k in current_names}

            # 2. Process Files
            # Create a unique key for the current settings to invalidate cache if settings change
            settings_key = f"{infill}_{walls}_{density}_{cost_per_kg}_{printer_name}"
            if "last_settings" not in st.session_state or st.session_state["last_settings"] != settings_key:
                 st.session_state["analyzed_files"] = {} # Clear cache if settings changed
                 st.session_state["last_settings"] = settings_key

            with st.status("Processing files...", expanded=True) as status:
                for stl in uploaded_stls:
                    if stl.name not in st.session_state["quantities"]:
                        st.session_state["quantities"][stl.name] = 1
                    
                    # Check if we already analyzed this file in this session
                    if stl.name in st.session_state["analyzed_files"]:
                        batch_results.append(st.session_state["analyzed_files"][stl.name])
                    else:
                        st.write(f"Analyzing {stl.name}...")
                        # FIXED: Read bytes for caching function and resetting pointer
                        stl.seek(0)
                        bytes_data = stl.read()
                        analysis = analyze_single_file_content(
                            bytes_data, stl.name, density, cost_per_kg, infill, walls,
                            printer["max_speed_mm_s"], printer["nozzle_mm"]
                        )
                        
                        if "error" not in analysis:
                            st.session_state["analyzed_files"][stl.name] = analysis
                            batch_results.append(analysis)
                        else:
                            st.error(f"Error processing {stl.name}: {analysis['error']}")
                
                status.update(label="Ready", state="complete", expanded=False)

    # --- BATCH RESULTS DISPLAY ---
    if batch_results:
        st.subheader("📦 Batch Analysis")
        
        total_cost_inr = 0
        total_weight = 0
        total_time = 0
        
        st.markdown("### Files")
        # FIXED: Enumerate to avoid key collisions
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
                with c1:
                    st.write(f"**{name}**")
                    st.caption(f"{item['Effective Volume (cm3)']} cm³ | {item['Print Time (hr)']} hr")
                with c2:
                    if st.button("➖", key=f"dec_{idx}_{name}"):
                        if st.session_state["quantities"][name] > 1:
                            st.session_state["quantities"][name] -= 1
                            st.rerun()
                with c3:
                    st.write(f"**Qty: {qty}**")
                with c4:
                     if st.button("➕", key=f"inc_{idx}_{name}"):
                         st.session_state["quantities"][name] += 1
                         st.rerun()
                st.divider()

        # Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Batch Cost (₹)", f"₹{total_cost_inr:,.0f}")
        c2.metric("Total Batch Weight", f"{total_weight:.1f} g")
        c3.metric("Total Print Time", f"{total_time:.1f} hr")

        # Quotation
        st.subheader("💰 Cost Quotation (₹ INR)")
        c_quote1, c_quote2 = st.columns(2)
        with c_quote1:
            machine_rate = st.number_input("Machine Rate (₹ / hr)", value=50)
            electricity_rate = st.slider("Electricity Rate (₹ / hr)", 0, 100, 10)
        with c_quote2:
            profit_pct = st.slider("Profit Margin (%)", 10, 100, 30)
            profit_margin = profit_pct / 100.0
            labour_rate = st.slider("Labour Charge (₹ / hr)", 0, 500, 50)
            
        gst_pct = st.number_input("GST (%)", value=0, min_value=0, max_value=28)
        gst_rate = gst_pct / 100.0

        quote = generate_quote(total_cost_inr, total_time, machine_rate, electricity_rate, labour_rate, profit_margin, gst_rate)
        st.table(pd.DataFrame(quote.items(), columns=["Item", "Amount (₹)"]))
        
        # Save to History
        total_items = sum(st.session_state["quantities"].values())
        if st.session_state.get("last_batch_len") != total_items:
             st.session_state["last_batch_len"] = total_items
             
             # Smart Naming Logic
             if len(batch_results) == 1:
                 entry_name = batch_results[0]["File Name"]
             else:
                 # If multiple files, list first few names or generic batch
                 names = [b["File Name"] for b in batch_results]
                 if len(names) <= 3:
                     entry_name = ", ".join(names)
                 else:
                     entry_name = f"Batch: {len(names)} files"

             add_history_entry(
                 entry_type="Estimation", # Changed from Batch Analysis to be cleaner
                 name=entry_name,
                 details=f"Cost: ₹{total_cost_inr:.0f} | Weight: {total_weight:.1f}g | Time: {total_time:.1f}hr",
                 cost=total_cost_inr
             )

        st.divider()
        col_actions1, col_actions2 = st.columns(2)
        
        with col_actions1:
            summary_text = f"Batch of {len(batch_results)} files. Total Cost: ₹{total_cost_inr:.0f}. Total Weight: {total_weight:.1f}g."
            display_ai_section(summary_text, button_label="🧠 Analyze Batch with AI")

        with col_actions2:
            batch_report_data = {
                "Report Type": "Batch Analysis",
                "Total Items": total_items,
                "Total Cost": f"₹{total_cost_inr:.0f}",
                "Total Weight": f"{total_weight:.1f} g",
            }
            batch_report_data.update(quote)
            pdf_buffer = export_pdf_report(batch_report_data)
            
            st.download_button(
                label="📄 Download Batch Report",
                data=pdf_buffer,
                file_name="batch_report.pdf",
                mime="application/pdf"
            )

    # --- LINK PARSER SECTION ---
    st.divider()
    st.header("🔗 Link Parser")
    model_url = st.text_input("Paste 3D Model URL")
    
    if st.button("🚀 Scrape & Analyze", type="primary"):
        if SAFE_MODE:
            st.warning("Scraping disabled in Safe Mode.")
        elif not model_url.strip():
            st.warning("Enter valid URL")
        else:
            with st.spinner("Scraping..."):
                scraped_data = scrape_model_page(model_url, debug=debug_mode)
                
                if scraped_data and "error" not in scraped_data:
                    st.success("Scraped!")
                    # AI Analysis
                    prompt = f"Analyze: {clean_scraped_text(scraped_data['text'])[:3000]}" # Limit text length
                    ai_result = ai_analyze(prompt)
                    
                    add_history_entry("Link Scraper", model_url, f"{len(scraped_data.get('images',[]))} imgs", 0.0, ai_result['summary'], ai_result['details'])
                    
                    st.markdown(f"**AI Summary:** {ai_result['summary']}")
                    st.markdown(ai_result["details"])
                    
                    if scraped_data.get("images"):
                        st.image(scraped_data["images"][:3], width=200) # Show first 3 images
                    
                    if scraped_data.get("stl_links"):
                         st.subheader("📥 STL Downloads")
                         for link in scraped_data["stl_links"]:
                             st.markdown(f"- [Download STL]({link})")
                    
                    # JSON Download
                    json_str = json.dumps(scraped_data, indent=2, default=str)
                    st.download_button("📥 Download JSON", json_str, "scraped_data.json", "application/json")
                else:
                    st.error(f"Failed: {scraped_data.get('error', 'Unknown error')}")
                    if debug_mode and scraped_data.get("debug"):
                         st.write(scraped_data["debug"])

    # --- HISTORY TAB ---
    with tab_history:
        st.header("📜 Analysis History")
        history_df = load_history()
        
        if not history_df.empty:
            history_df_reversed = history_df.iloc[::-1].reset_index(drop=True)
            for idx, row in history_df_reversed.iterrows():
                original_idx = len(history_df) - 1 - idx
                status = row.get("PrintStatus", "Pending")
                
                # Visual styling
                color = "#28a745" if status == "Print" else "#dc3545" if status == "Do Not Print" else "#ffc107"
                st.markdown(f"<div style='border-left: 5px solid {color}; padding-left: 10px;'>", unsafe_allow_html=True)
                
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{row['Type']}**: {row['Name']}")
                c1.caption(f"{row['Timestamp']} | {row['Details']}")
                c2.markdown(f"**{status}**")
                
                b1, b2 = st.columns(2)
                if b1.button("Print", key=f"p_{idx}"):
                    update_print_status(original_idx, "Print")
                    st.rerun()
                if b2.button("No Print", key=f"np_{idx}"):
                    update_print_status(original_idx, "Do Not Print")
                    st.rerun()
                
                st.markdown("</div><hr>", unsafe_allow_html=True)
                
            if st.button("🗑️ Clear History"):
                if os.path.exists("history.csv"):
                    os.remove("history.csv")
                    st.rerun()

if __name__ == "__main__":
    main()
