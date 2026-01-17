import streamlit as st
import pandas as pd
import time
import os
import json
from dotenv import load_dotenv

# Helper to load secrets locally if not on Render
if not os.path.exists(".streamlit/secrets.toml") and "gcp_service_account" not in st.secrets:
    # If you are running locally, you might want to mock this or rely on a local .toml file
    pass 

# Import modules
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags

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

    tab_web, tab_local, tab_bulk, tab_db = st.tabs(["🌐 Web Scout", "📂 Local Check", "📚 Bulk Learn", "🗄️ History"])

    # --- 1. WEB SCOUT (The Link Analyzer) ---
    with tab_web:
        url = st.text_input("Paste Model URL (MakerWorld, Printables, etc.)", placeholder="https://...")
        
        if st.button("🚀 Run Pre-Flight Check", type="primary"):
            past_failures = get_learning_context()
            
            with st.status("🤖 Companion Working...", expanded=True):
                st.write("1. 🕵️♂️ Scraping Comments & Makes...")
                data = scrape_model_page(url)
                if "error" in data: st.error(data['error']); st.stop()
                
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
                """
                
                ai_res = ai_analyze(prompt)
                tags = ai_generate_tags(ai_res['details'])
                
                st.session_state['res'] = ai_res
                st.session_state['imgs'] = data['images']
                st.session_state['url'] = url
                st.session_state['tags'] = tags
                
        # DISPLAY RESULTS
        if 'res' in st.session_state:
            res = st.session_state['res']
            
            # 1. VERDICT BANNER
            if "GO - EASY" in res['details']:
                st.markdown('<div class="success-box">✅ <strong>VERDICT: GO</strong> - This model looks safe to print.</div>', unsafe_allow_html=True)
            elif "CAUTION" in res['details']:
                st.markdown('<div class="warning-box">⚠️ <strong>VERDICT: CAUTION</strong> - Check the Red Flags below.</div>', unsafe_allow_html=True)
            
            # 2. CONTENT
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader("📋 Pre-Flight Plan")
                st.markdown(res['details'])
                st.info(f"🏷️ **Tags:** {st.session_state['tags']}")
            
            with c2:
                st.subheader("📸 Reality Check")
                if st.session_state['imgs']:
                    st.image(st.session_state['imgs'][:3], caption="User Makes")
                else:
                    st.warning("No user photos found.")
                
                if st.button("💾 Save to Brain"):
                    add_entry("Web Scrape", st.session_state['url'], res['details'], 0, res['summary'], st.session_state['tags'])
                    st.success("Saved! I'll remember this strategy.")

    # --- 2. LOCAL CHECK (STL Upload) ---
    with tab_local:
        st.info("Upload an STL. I'll check its geometry against your past failure patterns.")
        uploaded = st.file_uploader("Upload STL", accept_multiple_files=False)
        
        if uploaded and st.button("🧠 Check Geometry"):
            # Mock geometry check (would use trimesh in full app)
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

    # --- 3. BULK LEARN (Study Mode) ---
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

    # --- 4. HISTORY ---
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
