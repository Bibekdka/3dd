import asyncio
import sys
import streamlit as st
import pandas as pd
import time
import os
import io
import re
from dotenv import load_dotenv

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# IMPORTS
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags
from app_utils import export_pdf_report, analyze_single_file_content, slicer_volume_adjustment, estimate_print_time, generate_quote

load_dotenv()
st.set_page_config(page_title="AI Print Companion", page_icon="🤖", layout="wide")

# CSS
st.markdown("""
<style>
    .stButton>button { width: 100%; }
    .success-box { padding: 10px; background-color: #d4edda; border-radius: 5px; color: #155724; }
    .warning-box { padding: 10px; background-color: #fff3cd; border-radius: 5px; color: #856404; }
</style>
""", unsafe_allow_html=True)

PRINTER_PROFILES = {
    "Generic": {"speed": 60, "nozzle": 0.4},
    "Ender 3 / V2": {"speed": 50, "nozzle": 0.4},
    "Bambu P1/X1": {"speed": 120, "nozzle": 0.4},
    "Prusa MK3/4": {"speed": 70, "nozzle": 0.4}
}



def main():
    with st.sidebar:
        st.title("🧠 3D Brain")
        if os.getenv("GEMINI_API_KEY"): st.success("AI Online")
        else: st.error("AI Key Missing")
        
        with st.expander("📊 Stats", expanded=True):
            stats = get_db_stats()
            st.metric("Memories", stats['total'])
            st.metric("Success %", f"{stats['success_rate']}%")
        
        st.divider()
        printer_name = st.selectbox("Printer Profile", list(PRINTER_PROFILES.keys()))
        current_printer = PRINTER_PROFILES[printer_name]
        
        # COACH
        if st.button("🎓 Coach Me"):
            with st.spinner("Analyzing history..."):
                ctx = get_learning_context()
                advice = ai_analyze(f"Based on failures: {ctx}, give 3 tips.")
                # Structured Output Handling
                if advice.get('verdict') == "ERROR":
                     st.error(advice.get('summary'))
                else:
                     st.info(f"**Advice**: {advice.get('summary')}\n\n**Actionable Tips**: {advice.get('settings')}")

    # TABS
    tab_web, tab_calc, tab_local, tab_bulk, tab_db = st.tabs(["🌐 AI Scraper", "🚀 Calculator", "🛡️ Geometry Check", "📚 Bulk Internalize", "🗄️ History"])

    # --- 1. AI SCRAPER ---
    with tab_web:
        st.info("Paste Model URLs (One per line)")
        urls_input = st.text_area("Model URLs", placeholder="https://...", height=100)
        
        if st.button("🚀 Analyze Batch", type="primary"):
            urls = [u.strip() for u in urls_input.split('\n') if "http" in u]
            for i, url in enumerate(urls):
                with st.expander(f"Analysis {i+1}: {url}", expanded=(i==0)):
                    data = scrape_model_page(url)
                    if "error" in data: st.error(data['error']); continue
                    
                    past_failures = get_learning_context()
                    prompt = f"Memory: {past_failures}\nNew Data: {data['text']}"
                    
                    # New Structured Call
                    ai_res = ai_analyze(prompt)
                    
                    # Verdict Banner
                    v = ai_res.get('verdict', 'UNKNOWN')
                    if v == "GO":
                        st.success(f"✅ VERDICT: GO (Risk: {ai_res.get('risk_level', 'Low')})")
                    else:
                        st.error(f"🛑 VERDICT: STOP (Risk: {ai_res.get('risk_level', 'High')})")
                    
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.subheader("📝 Summary")
                        st.write(ai_res.get('summary', 'No summary'))
                        
                        st.subheader("⚠️ Warnings")
                        for w in ai_res.get('warnings', []): st.warning(w)

                        st.subheader("🔧 Settings")
                        for s in ai_res.get('settings', []): st.write(f"- {s}")
                        
                        tags = " ".join(ai_res.get('tags', []))
                        st.caption(f"Tags: {tags}")
                        
                    with c2:
                        if data['images']: st.image(data['images'][:2], caption="Makes")
                        
                        # Save
                        if st.button("💾 Save", key=f"s_{i}"):
                            # Flatten for DB
                            details = f"Summary: {ai_res.get('summary')}\nWarnings: {ai_res.get('warnings')}\nSettings: {ai_res.get('settings')}"
                            add_entry("Web Scrape", url, details, 0, ai_res.get('summary'), tags)
                            st.success("Saved!")

    # --- 2. CALCULATOR (Heavy/Light Split) ---
    with tab_calc:
        st.subheader("💰 Smart Quote")
        
        # SLIDERS (Light)
        c1, c2, c3, c4 = st.columns(4)
        infill = c1.slider("Infill %", 0, 100, 20)
        walls = c2.slider("Walls %", 0, 10, 3)
        cost_kg = c3.number_input("Cost/kg", value=1200)
        profit_pct = c4.slider("Profit %", 0, 200, 50)
        
        with st.expander("⚙️ Advanced Rates (GST, Labor, Delivery)"):
            rc1, rc2, rc3 = st.columns(3)
            elec_rate = rc1.number_input("Electricity (₹/hr)", 12.0)
            labor_rate = rc2.number_input("Labor (₹/hr)", 50.0)
            mach_rate = rc3.number_input("Machine (₹/hr)", 30.0)
            rc4, rc5 = st.columns(2)
            gst_rate = rc4.number_input("GST %", 18.0) / 100
            del_cost = rc5.number_input("Delivery (₹)", 0.0)

        # UPLOAD (Heavy)
        uploaded_files = st.file_uploader("Upload STLs", type=['stl'], accept_multiple_files=True)
        
        if uploaded_files:
            project_stats = []
            total_cost = 0
            total_time = 0
            
        # Helper for Caching
        @st.cache_data(show_spinner="Analyzing Mesh...", ttl=3600)
        def cached_analysis(file_bytes, file_name):
            return analyze_single_file_content(file_bytes, file_name)

        if uploaded_files:
            project_stats = []
            total_cost = 0
            total_time = 0
            
            for up_file in uploaded_files:
                # 1. HEAVY: Analyze Geometry (Cached)
                # Reads from RAM (bytes) -> Fast & Cached by Streamlit
                try:
                    geo = cached_analysis(up_file.getvalue(), up_file.name)
                except Exception as e:
                    st.error(f"Failed to analyze {up_file.name}: {e}")
                    continue
                
                if "error" in geo: st.error(f"{up_file.name}: {geo['error']}"); continue
                
                # 2. LIGHT: Calculate using Sliders
                raw_vol = geo["Raw Volume (cm3)"]
                eff_vol = slicer_volume_adjustment(raw_vol, infill, walls)
                weight = eff_vol * 1.24 # PLA density
                mat_cost_part = (weight / 1000) * cost_kg
                time_hr = estimate_print_time(eff_vol, 0.2, current_printer["speed"], current_printer["nozzle"])
                
                # Per Part Quote
                part_cost = mat_cost_part + (time_hr * mach_rate) + (time_hr * elec_rate) + (time_hr * labor_rate)
                part_price = (part_cost * (1 + profit_pct/100)) * (1 + gst_rate)
                
                project_stats.append({
                    "File": up_file.name,
                    "Weight": f"{weight:.1f}g",
                    "Time": f"{time_hr:.2f}h",
                    "Mat Cost": f"₹{mat_cost_part:.2f}",
                    "Raw Vol": raw_vol
                })
                total_cost += mat_cost_part
                total_time += time_hr
            
            # Project Totals
            q = generate_quote(total_cost, total_time, mach_rate, elec_rate, labor_rate, profit_pct/100, gst_rate, del_cost)
            
            st.divider()
            cA, cB = st.columns(2)
            with cA:
                st.metric("Project Total", f"₹{q['Final Price (₹)']}")
                st.dataframe(pd.DataFrame(project_stats))
            with cB:
                st.json(q)
            
            if st.button("📄 PDF Report"):
                pdf = export_pdf_report({"Parts": project_stats, "Quote": q})
                st.download_button("Download Quote", pdf, "quote.pdf", "application/pdf")

    # --- 3. GEOMETRY CHECK ---
    with tab_local:
        uploaded = st.file_uploader("Safety Check STL", key="safety_up")
        if uploaded and st.button("Check Safety"):
            mem = get_learning_context()
            prompt = f"User Past Failures: {mem}. File: {uploaded.name} ({uploaded.size/1e6:.1f}MB)."
            res = ai_analyze(prompt)
            # Adapt structured output to string for display
            display_text = f"**Verdict**: {res.get('verdict')}\n\n**Risk**: {res.get('risk_level')}\n\n**Analysis**: {res.get('summary')}\n\n**Warnings**: {res.get('warnings')}"
            st.markdown(display_text)

    # --- 4. BULK ---
    with tab_bulk:
        links_txt = st.text_area("Bulk Links")
        if st.button("Ingest All"):
            urls = [l for l in links_txt.split('\n') if "http" in l]
            prog = st.progress(0)
            for i, u in enumerate(urls):
                d = scrape_model_page(u)
                if "error" not in d:
                    r = ai_analyze(f"Context: {d['text'][:2000]}")
                    # Flat details for DB
                    flat_det = f"{r.get('summary')} | {r.get('verdict')}"
                    tags = " ".join(r.get('tags', []))
                    add_entry("Bulk", u, flat_det, 0, "Bulk", tags)
                prog.progress((i+1)/len(urls))
            st.success("Done!")

    # --- 5. HISTORY ---
    with tab_db:
        df = load_history()
        q = st.text_input("Filter History")
        if q and not df.empty: df = df[df['details'].str.contains(q, case=False)]
        
        st.dataframe(df)
        with st.expander("Edit Status"):
            rid = st.number_input("ID", min_value=0)
            if st.button("Mark Success"): update_print_status(rid, "Success")
            if st.button("Mark Fail"): update_print_status(rid, "Do Not Print")

if __name__ == "__main__":
    main()
