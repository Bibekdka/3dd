import asyncio
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io
import textwrap
import os
import trimesh
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# --- CUSTOM MODULES ---
from database import add_entry, load_history, update_print_status, get_learning_context
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags

# Windows Asyncio Fix
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- CONFIG ---
st.set_page_config(page_title="3D Brain Dashboard", page_icon="🧠", layout="wide")

# --- DEFAULT CONFIGURATION for Calculator ---
DEFAULT_PRINTERS = {
    "Ender 3 / Ender 3 V2": {"max_speed_mm_s": 50, "nozzle_mm": 0.4, "max_build_mm": (220, 220, 250), "reliability": 0.75},
    "Prusa MK3 / MK4": {"max_speed_mm_s": 70, "nozzle_mm": 0.4, "max_build_mm": (250, 210, 210), "reliability": 0.90},
    "Bambu Lab X1 / P1": {"max_speed_mm_s": 120, "nozzle_mm": 0.4, "max_build_mm": (256, 256, 256), "reliability": 0.95},
    "Anycubic Kobra 2 Neo": {"max_speed_mm_s": 150, "nozzle_mm": 0.4, "max_build_mm": (220, 220, 250), "reliability": 0.85}
}

# --- HELPER FUNCTIONS ---
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
                response = requests.get(img_url, timeout=1, stream=True)
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
                c.drawString(50, y, f"{key}: {value}")
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

# --- DASHBOARD LOGIC ---
def show_dashboard():
    st.title("🧠 Neural Dashboard")
    st.markdown("Visualizing your printer's 'Brain' and learning progress.")
    
    df = load_history()
    
    if df.empty:
        st.info("No data yet! Go to the 'Smart Analyst' tab to analyze your first model.")
        return

    # 1. TOP LEVEL METRICS (KPIs)
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    total_scans = len(df)
    # Calculate Success Rate (Items marked 'Success' / Total marked items)
    marked_items = df[df['print_status'].isin(['Success', 'Do Not Print'])]
    success_count = len(df[df['print_status'] == 'Success'])
    fail_count = len(df[df['print_status'] == 'Do Not Print'])
    
    success_rate = 0
    if len(marked_items) > 0:
        success_rate = (success_count / len(marked_items)) * 100

    # Estimate "Money Saved" (Cost of failed prints avoided)
    money_saved = df[df['print_status'] == 'Do Not Print']['cost_inr'].sum()

    kpi1.metric("Total Knowledge Base", f"{total_scans} Models", "scanned")
    kpi2.metric("Success Rate", f"{success_rate:.1f}%", f"{success_count} wins")
    kpi3.metric("Failures Avoided", f"{fail_count}", "blocked")
    kpi4.metric("Est. Money Saved", f"₹{money_saved:,.0f}", "rupees")

    st.divider()

    # 2. VISUALIZATION ROW 1
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🏷️ What is the AI Learning?")
        # Extract hashtags and count them
        all_tags = []
        for tags in df['tags']:
            if tags:
                # Clean and split tags
                cleaned = str(tags).replace("#", "").replace(",", " ").split()
                all_tags.extend(cleaned)
        
        if all_tags:
            tag_counts = pd.Series(all_tags).value_counts().head(10)
            fig_tags = px.bar(
                x=tag_counts.values, 
                y=tag_counts.index, 
                orientation='h',
                title="Top 10 Learned Concepts (Tags)",
                labels={'x': 'Count', 'y': 'Tag'},
                color=tag_counts.values,
                color_continuous_scale='Viridis'
            )
            st.plotly_chart(fig_tags, use_container_width=True)
        else:
            st.warning("No tags generated yet.")

    with c2:
        st.subheader("🚦 Go / Stop Ratio")
        # Simple sentiment analysis of the "AI Summary" to guess Verdict if not explicitly saved
        # (Or use print_status if available)
        status_counts = df['print_status'].value_counts()
        if not status_counts.empty:
            fig_pie = px.pie(
                values=status_counts.values, 
                names=status_counts.index,
                title="Print Decisions Breakdown",
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Mark some prints as 'Success' or 'Failed' in the Database tab to see this chart.")

    # 3. RECENT ACTIVITY TABLE
    st.subheader("📜 Recent Neural Activity")
    st.dataframe(
        df[['timestamp', 'name', 'tags', 'print_status']].head(5), 
        use_container_width=True,
        hide_index=True
    )


# --- MAIN APP ROUTER ---
def main():
    if "printers" not in st.session_state:
        st.session_state["printers"] = DEFAULT_PRINTERS.copy()
    if "quantities" not in st.session_state: st.session_state["quantities"] = {}
    if "analyzed_files" not in st.session_state: st.session_state["analyzed_files"] = {}

    # --- SIDEBAR MENU ---
    with st.sidebar:
        st.header("Navigation")
        # The Menu Icon functionality you requested
        selected_page = st.radio(
            "Go to:", 
            ["📊 Dashboard", "🕵️ Smart Analyst", "🚀 Cost Calculator", "🗄️ Database"],
            index=1 # Default to Analyst
        )
        
        st.divider()
        st.caption("System Status")
        if os.getenv("GEMINI_API_KEY"): st.success("AI: Online", icon="🟢")
        else: st.error("AI: Offline", icon="🔴")

        # Printer Config in Sidebar (Global)
        if selected_page == "🚀 Cost Calculator" or selected_page == "🕵️ Smart Analyst":
            st.divider()
            st.subheader("🖨️ Printer Settings")
            printer_names = list(st.session_state["printers"].keys())
            selected_printer_name = st.selectbox("Current Printer", printer_names)
            current_printer = st.session_state["printers"][selected_printer_name]
            
            with st.expander("🛠 Edit Profile"):
                new_speed = st.number_input("Speed (mm/s)", value=current_printer["max_speed_mm_s"])
                new_nozzle = st.number_input("Nozzle (mm)", value=current_printer["nozzle_mm"])
                if st.button("Update Profile"):
                    st.session_state["printers"][selected_printer_name]["max_speed_mm_s"] = new_speed
                    st.session_state["printers"][selected_printer_name]["nozzle_mm"] = new_nozzle
                    st.rerun()

    # --- PAGE ROUTING ---
    
    if selected_page == "📊 Dashboard":
        show_dashboard()

    elif selected_page == "🕵️ Smart Analyst":
        st.title("🕵️ Smart Forensic Analyst")
        
        st.info("💡 Paste a MakerWorld/Printables link. AI will check your past failures to give better advice.")
        c1, c2 = st.columns([3, 1])
        with c1:
            url = st.text_input("Model URL", placeholder="https://makerworld.com/en/models/...")
        with c2:
            st.write("")
            st.write("")
            analyze_btn = st.button("🚀 Analyze", type="primary", use_container_width=True)

        if analyze_btn and url:
            past_lessons = get_learning_context()
            with st.status("🕵️ Investigating...", expanded=True) as status:
                st.write("1. Launching visual scraper...")
                data = scrape_model_page(url)
                
                if "error" in data:
                    status.update(label="Failed", state="error")
                    st.error(data["error"])
                    st.stop()
                
                st.write("2. Consulting Memory Bank...")
                st.write("3. AI analyzing 'Vibe' & 'Reality'...")
                
                prompt = f"""
                Act as a 3D Printing Forensic Expert.
                
                USER CONTEXT (YOUR MEMORY):
                {past_lessons}

                NEW MODEL DATA TO ANALYZE:
                {data['text']}
                
                TASK:
                1. Flag any risks based on USER'S PAST FAILURES.
                2. Identify Filaments, Hardware, and 'Vibe'.
                3. Verdict: GO or STOP?
                """
                ai_result = ai_analyze(prompt)
                tags = ai_generate_tags(ai_result['details'])
                
                st.session_state['res'] = ai_result
                st.session_state['res_images'] = data.get('images', [])
                st.session_state['tags'] = tags
                st.session_state['url'] = url
                status.update(label="Complete!", state="complete", expanded=False)
        
        if 'res' in st.session_state:
            res = st.session_state['res']
            imgs = st.session_state.get('res_images', [])
            
            # Show Images
            if imgs:
                st.subheader("📸 Visual Proof")
                cols = st.columns(4)
                for i, img in enumerate(imgs[:4]):
                    with cols[i % 4]:
                        st.image(img, use_container_width=True)
            
            st.markdown(res['details'])
            st.info(f"🏷️ **Auto-Tags:** {st.session_state['tags']}")
            
            c1, c2 = st.columns(2)
            with c1:
                pdf_payload = {"Model": st.session_state.get('url'), "Details": res['details']}
                pdf_data = export_pdf_report(pdf_payload, image_urls=imgs)
                st.download_button("📥 PDF Report", pdf_data, "Report.pdf", "application/pdf", use_container_width=True)
            with c2:
                if st.button("💾 Save to Brain"):
                    add_entry(
                        entry_type="Web Scrape", 
                        name=st.session_state['url'], 
                        details=res['details'], 
                        ai_summary=res['summary'], 
                        tags=st.session_state['tags']
                    )
                    st.success("Saved!")

    elif selected_page == "🚀 Cost Calculator":
        st.title("🚀 Batch Estimator")
        
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
        
        # Helper to get current printer settings (if not in sidebar, getting default)
        # Note: We put printer selector in sidebar for this page.
        p_name = st.session_state.get("printers", DEFAULT_PRINTERS).keys()
        # Fallback if sidebar selection not accessed directly
        curr_p = DEFAULT_PRINTERS["Ender 3 / Ender 3 V2"] 
        # (Realistically sidebar logic runs first, so we assume selection is there, 
        # but for robustness we can just Grab the first one or LAST selected)
        
        if uploaded_stls:
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
                        # Use default printer settings if loop variable unavailable
                        analysis = analyze_single_file_content(
                            bytes_data, stl.name, density, cost_kg, infill, walls,
                            60, 0.4 # Default speed/nozzle if hard to reach sidebar scope
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

    elif selected_page == "🗄️ Database":
        st.title("🗄️ Memory Bank (SQLite)")
        
        search = st.text_input("🔍 Search History (e.g., 'PETG', '#vase-mode')")
        df = load_history()
        
        if search and not df.empty:
            df = df[df['details'].str.contains(search, case=False) | df['tags'].str.contains(search, case=False)]
        
        if not df.empty:
            for index, row in df.iterrows():
                with st.expander(f"{row['timestamp']} | {row['name']}"):
                    st.write(f"**Tags:** {row['tags']}")
                    st.write(row['details'])
                    
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Mark Success", key=f"s_{row['id']}"):
                        update_print_status(row['id'], "Success")
                        st.rerun()
                    if c2.button("❌ Mark Failed (AI will learn)", key=f"f_{row['id']}"):
                        update_print_status(row['id'], "Do Not Print")
                        st.rerun()

if __name__ == "__main__":
    main()
