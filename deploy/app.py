
import asyncio
import sys
import streamlit as st
import io
import pandas as pd
import requests
import time
import os

# FIX WINDOWS ASYNC LOOP
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# IMPORTS
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats, check_connection
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags

# --- CONFIGURATION & HELPERS ---
from app_utils import export_pdf_report, analyze_single_file_content, generate_quote 

PRINTER_PROFILES = {
    "Ender 3 / Ender 3 V2": {"max_speed_mm_s": 50, "nozzle_mm": 0.4},
    "Bambu Lab X1 / P1": {"max_speed_mm_s": 120, "nozzle_mm": 0.4},
    "Prusa MK3 / MK4": {"max_speed_mm_s": 70, "nozzle_mm": 0.4}
}

def main():
    st.set_page_config(page_title="3D Deep Dive Pro", page_icon="🧠", layout="wide")
    
    # --- SESSION STATE INIT ---
    if "printers" not in st.session_state: st.session_state["printers"] = PRINTER_PROFILES.copy()

    # --- SIDEBAR MENU (Fixed Visibility) ---
    with st.sidebar:
        st.title("🧠 3D Brain")
        
        # 1. CONNECTION STATUS INDICATOR
        if check_connection():
            st.success("🟢 Memory Online (G-Sheets)")
        else:
            st.error("🔴 Memory Offline (Check Secrets)")
            
        # 2. DASHBOARD (Moved out of Expander for Visibility)
        st.subheader("📊 Live Stats")
        stats = get_db_stats()
        c1, c2 = st.columns(2)
        c1.metric("Memories", f"{stats['total']}")
        c2.metric("Success", f"{stats['success_rate']}%")
        
        if stats['top_tags']:
            st.caption("Top Failure Tags:")
            st.bar_chart(pd.DataFrame(stats['top_tags'], columns=["Tag", "Cnt"]).set_index("Tag"))
            
        # 3. AI COACH BUTTON
        st.divider()
        if st.button("🎓 Coach Me"):
            with st.spinner("Analyzing history..."):
                history_text = get_learning_context()
                advice = ai_analyze(f"Based on history: {history_text}. Give 3 printing tips.")
                st.info(advice.get('details', advice.get('summary', 'No advice generated.')))

        st.divider()
        st.divider()
        # Printer Config
        printer_name = st.selectbox("Printer", list(st.session_state["printers"].keys()))
        
        # --- COST SETTINGS (Restored) ---
        with st.expander("💰 Cost Settings", expanded=True):
            cost_kg = st.number_input("Material Cost (₹/kg)", value=2000.0)
            machine_rate = st.number_input("Machine Rate (₹/hr)", value=50.0)
            elec_rate = st.number_input("Electricity Rate (₹/hr)", value=15.0)
            labor_rate = st.number_input("Labor Rate (₹/hr)", value=100.0)
            delivery_cost = st.number_input("Delivery Cost (₹)", value=100.0)
            margin = st.slider("Profit Margin (%)", 0, 200, 50)
            gst_rate = 0.18 # Fixed 18% GST default

        debug_mode = st.checkbox("Debug Mode")

    # --- CORE TABS (Preserved) ---
    tab_scrape, tab_local, tab_learn = st.tabs(["🕵️ Web Analyst", "💻 Local Estimator", "📚 Bulk Learning"])

    # --- TAB 1: WEB ANALYST ---
    with tab_scrape:
        st.header("🕵️ Web Forensic Analysis")
        url = st.text_input("Model URL")
        
        if st.button("🚀 Analyze", type="primary"):
            past_lessons = get_learning_context()
            
            with st.status("🤖 AI Agent Working...", expanded=True) as status:
                st.write("🔌 Connecting to Scraper...")
                
                # --- INJECTED FIX: Scraper Callback for Live Progress ---
                def update_status(msg):
                    st.write(msg)
                    time.sleep(0.05)
                
                # Pass callback to scraper
                data = scrape_model_page(url, status_callback=update_status)
                
                if "error" in data:
                    status.update(label="❌ Failed", state="error")
                    st.error(data["error"])
                    st.stop()
                
                st.write("🧠 Reading context...")
                prompt = f"""
                Analyze this model.
                MEMORY: {past_lessons}
                DATA: {data['text']}
                TASK: Verdict? Warn based on memory.
                """
                
                # Use Multimodal if available (Image Analysis)
                image_urls = data.get('images', [])
                try:
                    from ai import ai_analyze_multimodal
                    st.write(f"👁️ Visual Analysis on {len(image_urls)} images...")
                    ai_result = ai_analyze_multimodal(prompt, image_urls)
                except ImportError:
                     ai_result = ai_analyze(prompt)

                tags = ai_generate_tags(ai_result.get('details', ''))
                
                st.session_state['web_res'] = ai_result
                st.session_state['web_tags'] = tags
                st.session_state['web_url'] = url
                
                status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
                
        if 'web_res' in st.session_state:
            res = st.session_state['web_res']
            st.markdown(res.get('details', res.get('summary')))
            st.info(f"Tags: {st.session_state.get('web_tags')}")
            if st.button("💾 Save to Brain"):
                if add_entry("Web Scrape", st.session_state['web_url'], res.get('details'), 0, res.get('summary'), st.session_state.get('web_tags')):
                    st.success("Saved!")
                else:
                    st.error("Failed to save to Google Sheet. Check permissions.")

    # --- TAB 2: LOCAL ESTIMATOR ---
    with tab_local:
        st.header("💻 Local File Estimator")
        uploaded = st.file_uploader("Upload STL", type=["stl"], accept_multiple_files=True)
        if uploaded:
            st.write("---")
            for stl in uploaded:
                stl.seek(0); bytes_data = stl.read()
                
                # 1. Analyze Geometry & Basic Material Cost
                stats = analyze_single_file_content(
                    bytes_data, stl.name, 
                    density=1.24, 
                    cost_per_kg=cost_kg, 
                    infill=20, walls=3, 
                    speed_mm_s=60, nozzle_mm=0.4
                )
                
                if "error" not in stats:
                    # 2. Calculate Full Quote (Machine, Labor, etc.)
                    quote = generate_quote(
                        material_cost=stats['Cost (₹)'],
                        print_time_hr=stats['Print Time (hr)'],
                        machine_rate_per_hr=machine_rate,
                        electricity_per_hr=elec_rate,
                        labour_rate_per_hr=labor_rate,
                        profit_margin=margin/100,
                        gst=gst_rate,
                        delivery_cost=delivery_cost
                    )
                    
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.subheader(f"📄 {stl.name}")
                        st.metric("Final Price", f"₹{quote['Final Price (₹)']}")
                        st.caption(f"Time: {stats['Print Time (hr)']} hrs | Weight: {stats['Weight (g)']}g")
                    
                    with c2:
                        st.json(quote, expanded=False)
                        
                    if st.button("🧠 AI Check", key=f"ai_{stl.name}"):
                        mem = get_learning_context()
                        res = ai_analyze(f"Check safety for {stl.name} ({stats['Effective Volume (cm3)']}cm3). History: {mem}")
                        st.info(res.get('details', res.get('summary')))
                else:
                    st.error(f"Error analyzing {stl.name}: {stats['error']}")
                st.divider()
                st.divider()

    # --- TAB 3: BULK LEARNING ---
    with tab_learn:
        st.header("📚 Bulk Ingestion")
        raw_links = st.text_area("Paste Links (One per line)")
        if st.button("🚀 Process All"):
            links = [l.strip() for l in raw_links.split('\n') if "http" in l]
            prog = st.progress(0)
            for i, link in enumerate(links):
                data = scrape_model_page(link)
                if "error" not in data:
                    res = ai_analyze(f"Summarize: {data['text'][:2000]}")
                    tags = ai_generate_tags(res.get('details', ''))
                    add_entry("Bulk", link, res.get('details'), 0, res.get('summary'), tags)
                prog.progress((i + 1) / len(links))
            st.success("Batch Complete!")

if __name__ == "__main__":
    main()
