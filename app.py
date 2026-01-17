import asyncio
import sys
import streamlit as st
import pandas as pd
import time
import os

# FIX WINDOWS ASYNC LOOP
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# IMPORTS
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats, check_connection
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags
from app_utils import export_pdf_report, analyze_single_file_content 

PRINTER_PROFILES = {
    "Ender 3 / V2": {"speed": 50, "nozzle": 0.4},
    "Bambu P1/X1": {"speed": 120, "nozzle": 0.4},
    "Prusa MK3/4": {"speed": 70, "nozzle": 0.4}
}

def main():
    st.set_page_config(page_title="3D Deep Dive Pro", page_icon="🧠", layout="wide")
    if "printers" not in st.session_state: st.session_state["printers"] = PRINTER_PROFILES.copy()

    # --- SIDEBAR: The Brain Center ---
    with st.sidebar:
        st.title("🧠 3D Brain")
        
        # 1. Connection Check
        if check_connection():
            st.success("🟢 Connected to Memory")
        else:
            st.error("🔴 Offline (Check Secrets)")
            
        # 2. Stats Dashboard
        st.divider()
        stats = get_db_stats()
        c1, c2 = st.columns(2)
        c1.metric("Memories", f"{stats['total']}")
        c2.metric("Success", f"{stats['success_rate']}%")
        
        if stats['top_tags']:
            st.caption("Common Issues:")
            st.bar_chart(pd.DataFrame(stats['top_tags'], columns=["Tag", "Cnt"]).set_index("Tag"))

        # 3. AI Coach
        st.divider()
        if st.button("🎓 Coach Me"):
            with st.spinner("Reviewing failures..."):
                context = get_learning_context()
                advice = ai_analyze(f"Based on history: {context}, give 3 tips.")
                st.info(advice['details'])

        printer_name = st.selectbox("Printer", list(st.session_state["printers"].keys()))
        current_printer = st.session_state["printers"][printer_name]

        st.divider()
        st.caption("🔧 Print Settings")
        mat_type = st.selectbox("Material", ["PLA", "PETG", "TPU", "ABS"])
        infill = st.slider("Infill %", 10, 100, 20)
        walls = st.slider("Wall Volume %", 5, 100, 20)
        cost_kg = st.number_input("Cost/kg (₹)", 500, 5000, 1500)
        
        # Density Map
        densities = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21}
        density = densities[mat_type]

    # --- TABS: The Tools ---
    tab_scrape, tab_local, tab_learn = st.tabs(["🌐 Web Scout", "💻 Estimator", "📚 Bulk Learn"])

    # --- TAB 1: WEB SCOUT (Scrape + AI + Memory) ---
    with tab_scrape:
        st.header("🕵️ Forensic Analysis")
        url = st.text_input("Model URL (MakerWorld/Printables)")
        
        if st.button("🚀 Analyze", type="primary"):
            # A. Retrieve Memory
            memory = get_learning_context()
            
            with st.status("Running AI Agent...", expanded=True) as status:
                # B. Scrape Data
                def update_ui(msg): st.write(msg)
                data = scrape_model_page(url, status_callback=update_ui)
                
                if "error" in data:
                    status.update(label="❌ Failed", state="error")
                    st.error(data["error"])
                    st.stop()
                
                # C. AI Analysis (with Memory)
                st.write("🧠 Cross-referencing with past failures...")
                prompt = f"""
                Analyze this model.
                YOUR MEMORY (PAST FAILURES): {memory}
                NEW MODEL DATA: {data['text']}
                TASK: Warn if this model matches past failure patterns. Verdict?
                """
                res = ai_analyze(prompt)
                tags = ai_generate_tags(res['details'])
                
                st.session_state['res'] = res
                st.session_state['tags'] = tags
                st.session_state['url'] = url
                
                status.update(label="✅ Done!", state="complete", expanded=False)

        if 'res' in st.session_state:
            res = st.session_state['res']
            st.markdown(res['details'])
            st.info(f"Tags: {st.session_state['tags']}")
            if st.button("💾 Save to Memory"):
                if add_entry("Web Scrape", st.session_state['url'], res['details'], 0, res['summary'], st.session_state['tags']):
                    st.success("Saved!")
                else:
                    st.error("Save Failed.")

    # --- TAB 2: ESTIMATOR (Math + AI Check) ---
    with tab_local:
        st.header("💻 Cost & Safety Check")
        # Config moved to Sidebar
        uploaded = st.file_uploader("Upload STL", type=["stl"], accept_multiple_files=True)
        if uploaded:
            for stl in uploaded:
                stl.seek(0)
                stats = analyze_single_file_content(
                    stl.read(),
                    stl.name,
                    density,
                    cost_kg,
                    infill,
                    walls,
                    current_printer['speed'],
                    current_printer['nozzle']
                )
                
                if "error" not in stats:
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.write(f"**{stl.name}**")
                        st.caption(f"Cost: ₹{stats['Cost (₹)']} | Time: {stats['Print Time (hr)']}h")
                    with c2:
                        if st.button("🧠 AI Safety", key=f"ai_{stl.name}"):
                            mem = get_learning_context()
                            res = ai_analyze(f"Is {stl.name} ({stats['Effective Volume (cm3)']}cm3) safe? History: {mem}")
                            st.popover("Safety Report").markdown(res['details'])
                st.divider()

    # --- TAB 3: BULK (Loop) ---
    with tab_learn:
        st.header("📚 Bulk Ingestion")
        urls = st.text_area("Links (One per line)")
        if st.button("🚀 Process All"):
            link_list = [l.strip() for l in urls.split('\n') if "http" in l]
            prog = st.progress(0)
            for i, link in enumerate(link_list):
                data = scrape_model_page(link)
                if "error" not in data:
                    res = ai_analyze(f"Summarize: {data['text'][:2000]}")
                    tags = ai_generate_tags(res['details'])
                    add_entry("Bulk", link, res['details'], 0, res['summary'], tags)
                prog.progress((i + 1) / len(link_list))
            st.success("Bulk learning complete!")

if __name__ == "__main__":
    main()
