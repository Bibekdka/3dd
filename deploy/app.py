import streamlit as st
import pandas as pd
import time
import os
import json
from dotenv import load_dotenv

# FIX: Check os.environ (Render) instead of st.secrets to avoid crash
if not os.path.exists(".streamlit/secrets.toml") and "gcp_service_account" not in os.environ:
    # Logic to handle missing secrets (or just pass)
    pass 

# Import modules
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags
from app_utils import analyze_single_file_content, generate_quote, export_pdf_report
import io

load_dotenv()
st.set_page_config(page_title="AI Print Companion", page_icon="🤖", layout="wide")

# --- CSS FOR "COMPANION" VIBE ---
st.markdown("""
<style>
    .big-font { font-size:20px !important; }
    .success-box { border-left: 5px solid #28a745; background-color: #f0fff4; padding: 15px; border-radius: 5px; }
    .warning-box { border-left: 5px solid #ffc107; background-color: #fffbf0; padding: 15px; border-radius: 5px; }
    .error-box { border-left: 5px solid #dc3545; background-color: #fff5f5; padding: 15px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

def main():
    # --- SIDEBAR: THE BRAIN ---
    with st.sidebar:
        st.title("🤖 Companion")
        if os.getenv("GEMINI_API_KEY"): st.success("Brain Online", icon="🟢")
        else: st.error("Brain Offline (Check .env)", icon="🔴")
        
        # DASHBOARD
        with st.expander("📊 Knowledge Base", expanded=True):
            stats = get_db_stats()
            c1, c2 = st.columns(2)
            c1.metric("Memories", stats['total'])
            c2.metric("Success %", f"{stats['success_rate']}%")
            
            if stats['top_tags']:
                st.caption("Common Themes:")
                st.bar_chart(pd.DataFrame(stats['top_tags'], columns=["Tag", "Cnt"]).set_index("Tag"))
            
            # COACH BUTTON
            if st.button("🎓 Coach Me"):
                with st.spinner("Analyzing your history..."):
                    context = get_learning_context()
                    advice = ai_analyze(f"Based on these failures: {context}, give me 3 harsh but helpful tips to improve my printing.")
                    st.info(advice['details'])

    # --- MAIN UI ---
    st.title("🛡️ 3D Print Pre-Flight Center")
    st.markdown("I analyze models, check your history, and tell you *exactly* how to print them.")

    tab_web, tab_local, tab_calc, tab_bulk, tab_db = st.tabs(["🕵️ AI Scraper", "🛡️ Safety Check", "🚀 Calculator", "📚 Bulk Learn", "🗄️ History"])

    # --- 1. AI SCRAPER (Renamed) ---
    with tab_web:
        st.info("Paste Model URLs (One per line) to get AI Analysis using your Failure History.")
        urls_input = st.text_area("Model URLs", placeholder="https://...\nhttps://...", height=100)
        
        if st.button("🚀 Run Pre-Flight Check", type="primary"):
            past_failures = get_learning_context()
            urls = [u.strip() for u in urls_input.split('\n') if "http" in u]
            
            if not urls:
                st.warning("No valid URLs found.")
                st.stop()
            
            for i, url in enumerate(urls):
                with st.expander(f"Analysis {i+1}: {url}", expanded=(i==0)):
                    with st.status(f"🤖 Analyzing Model {i+1}...", expanded=True):
                        st.write("1. 🕵️♂️ Scraping Comments & Makes...")
                        data = scrape_model_page(url)
                        if "error" in data: 
                            st.error(data['error'])
                            continue
                        
                        st.write("2. 🧠 Comparing with your Failure History...")
                        
                        # THE COMPANION PROMPT
                        prompt = f"""
                        You are an expert 3D Printing Companion.
                        
                        USER MEMORY (PAST FAILURES):
                        {past_failures}
                        
                        NEW MODEL DATA (SCRAPED):
                        {data['text']}
                        
                        TASK:
                        1. **Pre-Flight Checklist**: Give a bulleted list of 5 settings to change immediately (Infill, Walls, Temp).
                        2. **Red Flags**: What are the common complaints in the comments? (e.g. "Legs snap off").
                        3. **Memory Check**: Does this model trigger any of the user's past failure patterns?
                        4. **Filament Choice**: What specific brand/color looks best in user photos?
                        5. **Verdict**: [GO - EASY] or [CAUTION - HARD].
                        
                        AT THE VERY END, generate 5 hashtags starting with # (e.g. #PLA #Easy).
                        """
                        
                        ai_res = ai_analyze(prompt)
                        
                        import re
                        tags = " ".join(re.findall(r"#\w+", ai_res['details']))
                        if not tags: tags = "#3dprinting"
                        
                        # DISPLAY IN EXPANDER
                        if "GO - EASY" in ai_res['details']:
                            st.markdown('<div class="success-box">✅ <strong>VERDICT: GO</strong></div>', unsafe_allow_html=True)
                        elif "CAUTION" in ai_res['details']:
                            st.markdown('<div class="warning-box">⚠️ <strong>VERDICT: CAUTION</strong></div>', unsafe_allow_html=True)
                            
                        c1, c2 = st.columns([2, 1])
                        with c1:
                            st.subheader("📋 Plan")
                            st.markdown(ai_res['details'])
                            st.info(f"🏷️ **Tags:** {tags}")
                        with c2:
                            if data['images']: st.image(data['images'][:2], caption="Makes")
                            if st.button("💾 Save", key=f"save_{i}"):
                                add_entry("Web Scrape", url, ai_res['details'], 0, ai_res['summary'], tags)
                                st.success("Saved!")

    # --- 2. LOCAL SAFETY CHECK (Geometry + AI) ---
    with tab_local:
        st.info("Upload an STL to check if its GEOMETRY matches your past failures (e.g. warping, thin walls).")
        uploaded = st.file_uploader("Upload STL for Safety Check", accept_multiple_files=False)
        
        if uploaded and st.button("🧠 Check Geometry"):
            f_size = uploaded.size / 1024 / 1024 # MB
            memory = get_learning_context()
            
            prompt = f"""
            User is trying to print a file named '{uploaded.name}' ({f_size:.1f} MB).
            
            USER PAST FAILURES:
            {memory}
            
            TASK:
            If the user has a history of failing with 'large' or 'complex' prints, and this file is large (>50MB), warn them.
            If they struggle with 'small parts' and the filename implies detail (e.g. 'miniature'), warn them.
            Otherwise, give a thumbs up.
            """
            advice = ai_analyze(prompt)
            st.markdown(advice['details'])

    # --- 3. COST CALCULATOR (Restored & Enhanced) ---
    with tab_calc:
        st.subheader("💰 Smart Quote Calculator")
        
        # Primary Inputs
        c1, c2, c3 = st.columns(3)
        mat_cost = c1.number_input("Material (₹/kg)", value=1200, step=50)
        speed = c2.number_input("Speed (mm/s)", value=60, step=10)
        profit = c3.slider("Profit Margin %", 0, 200, 50)
        
        # Advanced/Dynamic Rates
        with st.expander("⚙️ Operational Rates (Electricity, Labor, Tax)", expanded=False):
            rc1, rc2, rc3 = st.columns(3)
            elec_rate = rc1.number_input("Electricity (₹/hr)", value=12.0)
            labor_rate = rc2.number_input("Labor (₹/hr)", value=50.0)
            mach_rate = rc3.number_input("Machine Wear (₹/hr)", value=30.0)
            
            rc4, rc5 = st.columns(2)
            gst_rate = rc4.number_input("GST %", value=18.0) / 100
            delivery = rc5.number_input("Delivery/Packaging (₹)", value=0.0)

        uploaded_files = st.file_uploader("Upload STL(s) for Quote", type=['stl'], accept_multiple_files=True)
        
        if uploaded_files:
            file_stats = []
            total_cost = 0
            total_time = 0
            
            for up_file in uploaded_files:
                bytes_data = up_file.getvalue()
                stats = analyze_single_file_content(bytes_data, up_file.name, 1.24, mat_cost, 20, 3, speed, 0.4)
                if "error" not in stats:
                    file_stats.append(stats)
                    total_cost += stats['Cost (₹)']
                    total_time += stats['Print Time (hr)']
                else:
                    st.error(f"Error analyzing {up_file.name}: {stats['error']}")

            if file_stats:
                # Generate Project Quote
                q = generate_quote(
                    total_cost, 
                    total_time, 
                    mach_rate, 
                    elec_rate, 
                    labor_rate, 
                    profit/100, 
                    gst_rate,
                    delivery
                )
                
                # Display Results
                st.write("---")
                colA, colB = st.columns(2)
                with colA:
                    st.header(f"Total: ₹{q['Final Price (₹)']}")
                    st.caption(f"Project Quote for {len(file_stats)} parts")
                    st.dataframe(pd.DataFrame(file_stats))
                
                with colB:
                    st.subheader("B.O.M & Quote")
                    st.json(q)
                
                # PDF
                if st.button("📄 Download Project Report"):
                    # Create summary dict
                    summary_data = {"Project Breakdown": file_stats, "Total Quote": q}
                    pdf = export_pdf_report(summary_data)
                    st.download_button("Download Quote PDF", pdf, "project_quote.pdf", "application/pdf")

    # --- 4. BULK LEARN (Study Mode) ---
    with tab_bulk:
        st.header("📚 Bulk Ingestion")
        st.write("Paste a list of links. I will study them all and update my database.")
        links = st.text_area("Links (One per line)")
        
        if st.button("🚀 Study All"):
            urls = [l.strip() for l in links.split('\n') if "http" in l]
            prog = st.progress(0)
            
            for i, u in enumerate(urls):
                data = scrape_model_page(u)
                if "error" not in data:
                    res = ai_analyze(f"Summarize print settings and failures for: {data['text'][:3000]}")
                    tags = ai_generate_tags(res['details'])
                    add_entry("Bulk Learn", u, res['details'], 0, res['summary'], tags)
                prog.progress((i+1)/len(urls))
            
            st.success(f"✅ Learned from {len(urls)} models!")

    # --- 5. HISTORY ---
    with tab_db:
        st.subheader("🗄️ Memory Bank")
        df = load_history()
        
        # Search
        q = st.text_input("Search Memories")
        if q and not df.empty:
            df = df[df['details'].str.contains(q, case=False) | df['tags'].str.contains(q, case=False)]
            
        for i, row in df.iterrows():
            with st.expander(f"{row['timestamp']} | {row['name']}"):
                st.write(f"**Tags:** {row['tags']}")
                st.write(row['details'])
                c1, c2 = st.columns(2)
                if c1.button("✅ Success", key=f"s{i}"):
                    update_print_status(row['id'], "Success"); st.rerun()
                if c2.button("❌ Failed", key=f"f{i}"):
                    update_print_status(row['id'], "Do Not Print"); st.rerun()

if __name__ == "__main__":
    main()
