import asyncio
import sys
import streamlit as st
import io
import pandas as pd
import requests
import time

# FIX WINDOWS ASYNC LOOP
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# IMPORTS
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats
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
    if "quantities" not in st.session_state: st.session_state["quantities"] = {}
    if "analyzed_files" not in st.session_state: st.session_state["analyzed_files"] = {}

    # --- SIDEBAR BRAIN ---
    with st.sidebar:
        st.title("🧠 3D Brain")
        
        # 1. AI DASHBOARD
        with st.expander("📊 Brain Dashboard", expanded=False):
            stats = get_db_stats()
            c1, c2 = st.columns(2)
            c1.metric("Memory", f"{stats['total']}")
            c2.metric("Success", f"{stats['success_rate']}%")
            
            if stats['top_tags']:
                st.caption("Common Themes:")
                st.bar_chart(pd.DataFrame(stats['top_tags'], columns=["Tag", "Cnt"]).set_index("Tag"))
            
            # THE AI COACH (New Feature)
            st.divider()
            if st.button("🎓 Coach Me (Analyze Trends)"):
                with st.spinner("Reviewing your history..."):
                    history_text = get_learning_context() # Gets recent failures
                    prompt = f"""
                    Look at this user's 3D printing history:
                    {history_text}
                    
                    Identify patterns in their failures.
                    Suggest 3 specific improvements (e.g., "Dry your PETG", "Slow down walls").
                    Keep it short and punchy.
                    """
                    advice = ai_analyze(prompt)
                    st.success("Coach's Advice:")
                    st.info(advice['details'])

        st.divider()
        # Printer Select
        printer_name = st.selectbox("Printer", list(st.session_state["printers"].keys()))
        current_printer = st.session_state["printers"][printer_name]
        debug_mode = st.checkbox("Debug Mode")

    # --- TABS ---
    tab_scrape, tab_local, tab_learn = st.tabs(["🕵️ Web Analyst", "💻 Local Estimator", "📚 Bulk Learning"])

    # --- TAB 1: WEB ANALYST (Keep existing logic) ---
    with tab_scrape:
        st.header("🕵️ Web Forensic Analysis")
        url = st.text_input("Model URL")
        if st.button("🚀 Analyze"):
            past_lessons = get_learning_context()
            with st.status("Consulting Brain...", expanded=True):
                data = scrape_model_page(url, debug=debug_mode)
                if "error" in data:
                    st.error(data["error"]); st.stop()
                
                # Using tags from database to do intelligent comparison
                prompt = f"""
                Analyze this model.
                
                MEMORY (USER FAILURES):
                {past_lessons}
                
                NEW MODEL DATA:
                {data['text']}
                
                TASK:
                1. Warn based on exact tags in MEMORY (e.g., if memory has #petg #warp, and this is PETG, warn).
                2. Verdict?
                """
                ai_result = ai_analyze(prompt)
                tags = ai_generate_tags(ai_result['details'])
                
                st.session_state['web_res'] = ai_result
                st.session_state['web_tags'] = tags
                st.session_state['web_url'] = url
                
        if 'web_res' in st.session_state:
            res = st.session_state['web_res']
            st.markdown(res['details'])
            st.info(f"Tags: {st.session_state['web_tags']}")
            if st.button("💾 Save to Brain"):
                add_entry("Web Scrape", st.session_state['web_url'], res['details'], 0, res['summary'], st.session_state['web_tags'])
                st.success("Saved!")

    # --- TAB 2: LOCAL ESTIMATOR (New AI Integration) ---
    with tab_local:
        st.header("💻 Local File Estimator + AI Safety Check")
        
        # Config
        c1, c2, c3 = st.columns(3)
        infill = c1.slider("Infill %", 10, 100, 20)
        walls = c2.slider("Walls %", 1, 10, 3) 
        mat_type = c3.selectbox("Material", ["PLA", "PETG", "TPU", "ABS"])
        
        uploaded = st.file_uploader("Upload STL", type=["stl"], accept_multiple_files=True)
        
        if uploaded:
            st.divider()
            for stl in uploaded:
                # 1. Calculate Math
                stl.seek(0); bytes_data = stl.read()
                stats = analyze_single_file_content(bytes_data, stl.name, 1.24, 20, infill, walls*25, 60, 0.4)
                
                if "error" not in stats:
                    # Display Math
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.write(f"**{stl.name}**")
                        st.caption(f"Vol: {stats['Effective Volume (cm3)']}cm³ | Time: {stats['Print Time (hr)']}h | Cost: ₹{stats['Cost (₹)']}")
                    
                    # 2. AI SAFETY CHECK (The New Feature)
                    with c2:
                        if st.button(f"🧠 AI Check", key=f"ai_{stl.name}"):
                            # Construct a "Digital Twin" description for the AI
                            file_desc = f"""
                            Object: {stl.name}
                            Material: {mat_type}
                            Volume: {stats['Effective Volume (cm3)']} cm3
                            Print Time: {stats['Print Time (hr)']} hours
                            Infill: {infill}%
                            """
                            
                            # Get Memory
                            memory = get_learning_context()
                            
                            prompt = f"""
                            You are a Print Safety AI. 
                            USER HISTORY (FAILURES):
                            {memory}
                            
                            CURRENT PRINT JOB:
                            {file_desc}
                            
                            TASK:
                            Predict if this print will fail based on the User History and the Geometry/Material.
                            Example: If history says "PETG warps on large prints" and this is a large PETG print, Warn them.
                            """
                            
                            with st.spinner("Checking geometry against memory..."):
                                analysis = ai_analyze(prompt)
                                st.popover("AI Safety Report").markdown(analysis['details'])
                st.divider()

    # --- TAB 3: BULK LEARNING (New Feature) ---
    with tab_learn:
        st.header("📚 Bulk Learning & Ingestion")
        st.info("Paste a list of URLs (one per line). The AI will study them all and update its Brain.")
        
        raw_links = st.text_area("Paste Links Here", height=150)
        
        if st.button("🚀 Start Bulk Study"):
            links = [l.strip() for l in raw_links.split('\n') if "http" in l]
            
            if not links:
                st.warning("No valid links found.")
                st.stop()
            
            progress = st.progress(0)
            status = st.empty()
            
            for i, link in enumerate(links):
                status.write(f"Studying {i+1}/{len(links)}: {link}...")
                
                # 1. Scrape
                data = scrape_model_page(link)
                if "error" in data:
                    st.error(f"Skipped {link}: {data['error']}")
                    continue
                    
                # 2. Analyze
                prompt = f"Extract key print settings and failure points from this text: {data['text'][:3000]}"
                ai_res = ai_analyze(prompt)
                tags = ai_generate_tags(ai_res['details'])
                
                # 3. Save to Brain
                add_entry("Bulk Learn", link, ai_res['details'], 0, ai_res['summary'], tags)
                
                progress.progress((i + 1) / len(links))
                time.sleep(1) # Polite delay
            
            status.success(f"✅ Learned from {len(links)} new sources!")
            st.balloons()

if __name__ == "__main__":
    main()
