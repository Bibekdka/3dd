import asyncio
import sys
import streamlit as st
import io
import pandas as pd
import requests
import textwrap
import os
import trimesh
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# IMPORTS
from database import add_entry, load_history, update_print_status, get_learning_context, get_db_stats
from scraper import scrape_model_page
from ai import ai_analyze, ai_generate_tags

# --- FIX WINDOWS LOOP ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- CONFIG ---
st.set_page_config(page_title="3D Deep Dive Pro", page_icon="🧠", layout="wide")

# --- PRINTER PROFILES & HELPER FUNCTIONS ---
DEFAULT_PRINTERS = {
    "Ender 3 / Ender 3 V2": {"max_speed_mm_s": 50, "nozzle_mm": 0.4},
    "Prusa MK3 / MK4": {"max_speed_mm_s": 70, "nozzle_mm": 0.4},
    "Bambu Lab X1 / P1": {"max_speed_mm_s": 120, "nozzle_mm": 0.4},
    "Anycubic Kobra 2 Neo": {"max_speed_mm_s": 150, "nozzle_mm": 0.4}
}

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

def main():
    if "printers" not in st.session_state:
        st.session_state["printers"] = DEFAULT_PRINTERS.copy()
    if "quantities" not in st.session_state: st.session_state["quantities"] = {}
    if "analyzed_files" not in st.session_state: st.session_state["analyzed_files"] = {}

    # --- SIDEBAR MENU & DASHBOARD ---
    with st.sidebar:
        st.title("🧠 3D Brain")
        
        # 1. THE DASHBOARD MENU (New)
        with st.expander("📊 AI Learning Dashboard", expanded=False):
            stats = get_db_stats()
            
            # Metrics Row
            c1, c2 = st.columns(2)
            c1.metric("Memory Bank", f"{stats['total']} Items")
            c2.metric("Success Rate", f"{stats['success_rate']}%")
            
            st.divider()
            
            # Failure Analysis
            st.caption("⚠️ Risk Factors (Tags in Failures)")
            if stats['top_tags']:
                tags_df = pd.DataFrame(stats['top_tags'], columns=["Tag", "Count"])
                st.bar_chart(tags_df.set_index("Tag"))
            
            # Live "Memory" Feed
            st.divider()
            st.caption("🧠 Active Memory (Input to AI):")
            memory_context = get_learning_context()
            if memory_context:
                st.code(memory_context, language="text")
            else:
                st.info("Memory is empty.")

        st.divider()
        
        if os.getenv("GEMINI_API_KEY"): st.success("AI Connected", icon="✅")
        
        # Printer Config
        printer_names = list(st.session_state["printers"].keys())
        selected_printer_name = st.selectbox("Printer", printer_names)
        current_printer = st.session_state["printers"][selected_printer_name]
        
        with st.expander("🛠 Edit Profile"):
            new_speed = st.number_input("Speed (mm/s)", value=current_printer["max_speed_mm_s"])
            new_nozzle = st.number_input("Nozzle (mm)", value=current_printer["nozzle_mm"])
            if st.button("Update"):
                st.session_state["printers"][selected_printer_name]["max_speed_mm_s"] = new_speed
                st.session_state["printers"][selected_printer_name]["nozzle_mm"] = new_nozzle
                st.rerun()

        debug_mode = st.checkbox("Debug Mode")

    # --- MAIN TABS ---
    tab_scrape, tab_est, tab_hist = st.tabs(["🕵️ Smart Analyst", "🚀 Estimator", "📜 Memory Bank"])

    # --- TAB 1: ANALYST ---
    with tab_scrape:
        st.header("🕵️ Forensic Analysis")
        st.caption("AI uses the 'Active Memory' from the sidebar to warn you about past mistakes.")
        
        url = st.text_input("Model URL", placeholder="https://makerworld.com/...")
        
        if st.button("🚀 Analyze with AI Memory", type="primary"):
            past_lessons = get_learning_context()
            
            with st.status("Consulting Brain...", expanded=True):
                st.write("1. Scraping visual data...")
                data = scrape_model_page(url, debug=debug_mode)
                
                if "error" in data:
                    st.error(data["error"])
                    st.stop()
                
                st.write("2. Comparing with Memory Bank...")
                prompt = f"""
                Analyze this 3D model.
                
                YOUR MEMORY (USER'S PAST FAILURES):
                {past_lessons}
                
                NEW MODEL DATA:
                {data['text']}
                
                TASK:
                1. CHECK MEMORY: If the user failed similar prints (e.g., matching tags like #petg or #articulated), WARN THEM BOLDLY.
                2. Reality Check: Compare User Comments vs Description.
                3. Verdict: GO or STOP?
                """
                ai_result = ai_analyze(prompt)
                tags = ai_generate_tags(ai_result['details'])
                
                st.session_state['result'] = ai_result
                st.session_state['tags'] = tags
                st.session_state['url'] = url
                st.session_state['images'] = data.get('images', [])

        if 'result' in st.session_state:
            res = st.session_state['result']
            st.success("Analysis Complete")
            
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(res['details'])
                st.info(f"🏷️ **Auto-Tags:** {st.session_state['tags']}")
            
            with c2:
                if st.session_state.get('images'):
                    st.image(st.session_state['images'][:3], caption="Visual Proof")
                
                if st.button("💾 Save to Memory"):
                    add_entry("Web Scrape", st.session_state['url'], res['details'], 0, res['summary'], st.session_state['tags'])
                    st.toast("Saved! AI will learn from this.", icon="🧠")
                
                pdf_payload = {"Model": st.session_state.get('url'), "Details": res['details']}
                pdf_data = export_pdf_report(pdf_payload, image_urls=st.session_state.get('images', []))
                st.download_button("📥 Report", pdf_data, "Report.pdf", "application/pdf")

    # --- TAB 2: ESTIMATOR (Restored) ---
    with tab_est:
        st.header("🚀 Batch Estimator")
        with st.expander("⚙️ Estimation Settings", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                infill = st.slider("Infill %", 0, 100, 20)
                walls = st.slider("Walls %", 0, 100, 25)
            with col2:
                density = st.number_input("Density (g/cm³)", value=1.24)
                cost_kg = st.number_input("Cost (₹/kg)", value=1200.0)
            with col3:
                profit = st.number_input("Margin (%)", value=30)
                
        uploaded_stls = st.file_uploader("Upload STLs", type=["stl"], accept_multiple_files=True)
        batch_results = []
        
        if uploaded_stls:
            st.session_state["quantities"] = {k: v for k, v in st.session_state["quantities"].items() if k in [f.name for f in uploaded_stls]}
            
            for stl in uploaded_stls:
                name = stl.name
                if name not in st.session_state["quantities"]: st.session_state["quantities"][name] = 1
                if name not in st.session_state["analyzed_files"]:
                    stl.seek(0)
                    analysis = analyze_single_file_content(stl.read(), name, density, cost_kg, infill, walls, current_printer["max_speed_mm_s"], current_printer["nozzle_mm"])
                    if "error" not in analysis: st.session_state["analyzed_files"][name] = analysis
                
                if name in st.session_state["analyzed_files"]: batch_results.append(st.session_state["analyzed_files"][name])

            if batch_results:
                 total_c = 0
                 for idx, item in enumerate(batch_results):
                     name = item["File Name"]
                     qty = st.session_state["quantities"][name]
                     total_c += item["Cost (₹)"] * qty
                     c1, c2, c3 = st.columns([3,1,1])
                     c1.write(f"**{name}** (₹{item['Cost (₹)']})")
                     if c2.button("➖", key=f"m{idx}") and qty > 1:
                         st.session_state["quantities"][name] -= 1
                         st.rerun()
                     c3.write(f"Qty: {qty}")
                     if c3.button("➕", key=f"p{idx}"):
                         st.session_state["quantities"][name] += 1
                         st.rerun()
                 
                 st.info(f"Total Base Cost: ₹{round(total_c, 2)}")

    # --- TAB 3: MEMORY BANK ---
    with tab_hist:
        st.header("📜 Database Management")
        
        search = st.text_input("🔍 Search Memory (e.g., '#fail', 'PETG')")
        df = load_history()
        
        if search and not df.empty:
            df = df[df['details'].str.contains(search, case=False) | df['tags'].str.contains(search, case=False)]
        
        st.dataframe(
            df, 
            column_config={
                "print_status": st.column_config.SelectboxColumn(
                    "Status",
                    help="Did it print?",
                    width="medium",
                    options=["Pending", "Success", "Do Not Print"],
                    required=True,
                )
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.caption("Change 'Status' to 'Do Not Print' to teach the AI that this was a failure.")
        
        col1, col2 = st.columns(2)
        with col1:
            row_id = st.number_input("ID to Update", min_value=0, step=1)
        with col2:
            new_status = st.selectbox("New Status", ["Success", "Do Not Print", "Pending"])
            if st.button("Update Training Data"):
                update_print_status(row_id, new_status)
                st.rerun()

if __name__ == "__main__":
    main()
