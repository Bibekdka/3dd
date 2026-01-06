import streamlit as st
import trimesh
import os
import tempfile
import pandas as pd
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Import from new modules
from scraper import scrape_model_page, clean_scraped_text
from ai import ai_analyze
from history import load_history, add_history_entry

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
    }
}

def export_pdf_report(data):
    path = "print_report.pdf"
    c = canvas.Canvas(path, pagesize=A4)
    y = 800

    c.setFont("Helvetica", 14)
    c.drawString(40, 820, "3D Slicer Volume Estimator Report")
    
    c.setFont("Helvetica", 11)

    # Handle dictionary (single report) or generic text
    if isinstance(data, dict):
        for key, value in data.items():
            c.drawString(40, y, f"{key}: {value}")
            y -= 25
            if y < 50:
                c.showPage()
                y = 800
    else:
        # Simple text dump for now if not dict
        text_lines = str(data).split('\n')
        for line in text_lines:
            c.drawString(40, y, line)
            y -= 20
            if y < 50:
                c.showPage()
                y = 800

    c.save()
    return path

def display_ai_section(prompt_text, button_label="Generate AI Assessment"):
    """
    Helper to render AI button and results to avoid code duplication.
    """
    if st.button(button_label):
        with st.spinner("Consulting Gemini..."):
            ai_result = ai_analyze(prompt_text)

        if ai_result["mode"] == "live":
            st.success("Gemini AI Analysis")
            st.markdown(ai_result["analysis"])
        else:
            st.warning("Using mock AI output (Check API Key or Connection)")
            st.json(ai_result)

def slicer_volume_adjustment(
    mesh_volume_cm3,
    infill_percent=20,
    wall_percent=25
):
    """
    Realistic slicer approximation:
    - walls/top/bottom are solid
    - infill only affects inner volume
    """
    wall_fraction = wall_percent / 100
    infill_fraction = infill_percent / 100

    wall_volume = mesh_volume_cm3 * wall_fraction
    internal_volume = mesh_volume_cm3 * (1 - wall_fraction)

    effective_volume = wall_volume + (internal_volume * infill_fraction)

    return effective_volume

def estimate_print_time(
    effective_volume_cm3,
    layer_height=0.2,
    printer_speed_mm_s=60,
    nozzle_mm=0.4
):
    """
    Practical print-time estimator (farm-tested logic)
    """
    extrusion_rate = printer_speed_mm_s * layer_height * nozzle_mm
    total_mm3 = effective_volume_cm3 * 1000

    seconds = total_mm3 / extrusion_rate
    hours = seconds / 3600

    return round(hours, 2)

def analyze_stl(file_path, density, cost_per_kg, infill, walls, speed_mm_s=60, nozzle_mm=0.4):
    try:
        mesh = trimesh.load(file_path)
        
        if not mesh.is_watertight:
            # We can log this but for batch just return stats
            pass
        
        volume_raw = mesh.volume
        volume_cm3 = volume_raw / 1000.0
        
        effective_volume = slicer_volume_adjustment(
            volume_cm3, 
            infill_percent=infill, 
            wall_percent=walls
        )
        
        weight_g = effective_volume * density
        cost = (weight_g / 1000) * cost_per_kg
        
        # Calculate print time
        print_time = estimate_print_time(
            effective_volume, 
            printer_speed_mm_s=speed_mm_s,
            nozzle_mm=nozzle_mm
        )
        
        return {
            "Raw Volume (cm3)": round(volume_cm3, 2),
            "Effective Volume (cm3)": round(effective_volume, 2),
            "Weight (g)": round(weight_g, 2),
            "Cost ($)": round(cost, 2),
            "Print Time (hr)": print_time,
            "Vertices": len(mesh.vertices),
            "Faces": len(mesh.faces),
            "Watertight": mesh.is_watertight
        }
    except Exception as e:
        return None

def generate_quote(
    material_cost,
    print_time_hr,
    machine_rate_per_hr=50,   # ₹
    electricity_per_hr=10,    # ₹
    profit_margin=0.30,       # 30%
    gst=0.0                   # Default 0% (Optional)
):
    base_cost = (
        material_cost +
        (print_time_hr * machine_rate_per_hr) +
        (print_time_hr * electricity_per_hr)
    )

    profit = base_cost * profit_margin
    subtotal = base_cost + profit
    gst_amount = subtotal * gst

    total = subtotal + gst_amount

    return {
        "Material Cost (₹)": round(material_cost, 2),
        "Machine Cost (₹)": round(print_time_hr * machine_rate_per_hr, 2),
        "Electricity (₹)": round(print_time_hr * electricity_per_hr, 2),
        "Profit (₹)": round(profit, 2),
        "GST (₹)": round(gst_amount, 2),
        "Final Price (₹)": round(total, 2)
    }

def main():
    st.set_page_config(page_title="3D Slicer Volume Estimator", page_icon="🧊")

    st.title("🧊 3D Slicer Volume Estimator")
    
    # Sidebar for API Status
    with st.sidebar:
        if os.getenv("GEMINI_API_KEY"):
            st.success("Gemini API Key Detected", icon="✅")
        else:
            st.warning("Gemini API Key Missing", icon="⚠️")
        
        st.divider()
        debug_mode = st.sidebar.checkbox("🛠 Scraper Debug Mode")
        
        st.sidebar.subheader("🖨️ Printer Profile")
        printer_name = st.sidebar.selectbox(
            "Select Printer",
            list(PRINTER_PROFILES.keys())
        )
        printer = PRINTER_PROFILES[printer_name]

    st.markdown("""
    Upload STL files to calculate volume and estimate the *effective* cost/weight 
    based on your slicer settings.
    """)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Slicer Settings")
        
        infill = st.slider("Infill Percentage (%)", 0, 100, 20)
        walls = st.slider("Wall/Shell Percentage (%)", 0, 100, 25)
    
    with col2:
        st.subheader("Material Settings")
        density = st.number_input("Material Density (g/cm3)", value=1.24) # PLA Default
        cost_per_kg = st.number_input("Cost per kg ($)", value=20.0)

    tab_estimator, tab_history = st.tabs(["🚀 Estimator", "📜 History"])

    with tab_estimator:
        uploaded_stls = st.file_uploader(
            "Upload multiple STL files",
            type=["stl"],
            accept_multiple_files=True
        )

        batch_results = []

    if uploaded_stls:
        with st.status("Processing files...", expanded=True) as status:
            for stl in uploaded_stls:
                st.write(f"Analyzing {stl.name}...")
                # Write temp file for trimesh
                with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as tmp:
                    tmp.write(stl.read())
                    tmp_path = tmp.name
                
                try:
                    analysis = analyze_stl(
                        tmp_path, density, cost_per_kg, infill, walls, 
                        speed_mm_s=printer["max_speed_mm_s"],
                        nozzle_mm=printer["nozzle_mm"]
                    )
                    if analysis:
                        analysis["File Name"] = stl.name
                        batch_results.append(analysis)
                    
                    # Cleanup
                    os.remove(tmp_path)
                except Exception as e:
                    st.error(f"Error processing {stl.name}: {e}")
            
            status.update(label="Processing Complete!", state="complete", expanded=False)

    if batch_results:
        st.subheader("📦 Batch Analysis")
        # Reorder columns to put File Name first
        df = pd.DataFrame(batch_results)
        cols = ["File Name"] + [c for c in df.columns if c != "File Name"]
        df = df[cols]
        
        st.dataframe(df, use_container_width=True)
        
        # Summary Metrics
        total_cost = df["Cost ($)"].sum()
        total_weight = df["Weight (g)"].sum()
        total_time = df["Print Time (hr)"].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Batch Cost", f"${total_cost:.2f}")
        c2.metric("Total Batch Weight", f"{total_weight:.1f} g")
        c3.metric("Total Print Time", f"{total_time:.1f} hr")

        # Cost Quotation UI
        st.subheader("💰 Cost Quotation (₹ INR)")
        c_quote1, c_quote2 = st.columns(2)
        with c_quote1:
            machine_rate = st.number_input("Machine Rate (₹ / hr)", value=50)
        with c_quote2:
            profit_pct = st.slider("Profit Margin (%)", 10, 100, 30)
            profit_margin = profit_pct / 100.0
            
        gst_pct = st.number_input("GST (%)", value=0, min_value=0, max_value=28, help="Enter 18 for standard GST")
        gst_rate = gst_pct / 100.0

        quote = generate_quote(
            material_cost=total_cost * 83,  # USD to INR approx
            print_time_hr=total_time,
            machine_rate_per_hr=machine_rate,
            profit_margin=profit_margin,
            gst=gst_rate
        )
        
        st.table(pd.DataFrame(quote.items(), columns=["Item", "Amount (₹)"]))
        
        # Save to History
        if st.session_state.get("last_batch_len") != len(batch_results):
             st.session_state["last_batch_len"] = len(batch_results)
             add_history_entry(
                 entry_type="Batch Analysis",
                 name=f"{len(batch_results)} files",
                 details=f"Cost: ${total_cost:.2f}, Weight: {total_weight:.1f}g",
                 cost=total_cost * 83
             )

        # Batch features (AI + PDF)
        st.divider()
        
        col_actions1, col_actions2 = st.columns(2)
        
        with col_actions1:
            summary_text = f"""
            Batch Analysis of {len(batch_results)} files:
            Total Cost: ${total_cost:.2f}
            Total Weight: {total_weight:.1f}g
            
            Files Overview:
            {df.to_string(index=False)}
            
            Provide a summary recommendation for this production batch.
            """
            display_ai_section(summary_text, button_label="🧠 Analyze Batch with AI")

        with col_actions2:
            # Generate Text/PDF report for batch
            batch_report_data = {
                "Report Type": "Batch Analysis",
                "File Count": len(batch_results),
                "Total Cost": f"${total_cost:.2f}",
                "Total Weight": f"{total_weight:.1f} g",
                "Infill": f"{infill}%",
                "Density": f"{density} g/cm3",
            }
            batch_report_data.update(quote) # Add financial quote to PDF
            pdf_path = export_pdf_report(batch_report_data)
            
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📄 Download Batch Report",
                    data=f,
                    file_name="batch_report.pdf",
                    mime="application/pdf"
                )

    # Link Parser Section
    st.divider()
    st.header("🔗 Link Parser (Universal Scraper)")
    st.markdown("Supports MakerWorld, Printables, Thangs, Thingiverse, etc. Pasting a link scrapes images, settings, and reviews for AI analysis.")
    
    model_url = st.text_input("Paste 3D Model URL")
    
    if st.button("🚀 Scrape & Analyze", type="primary"):
        if not model_url.strip():
            st.warning("Please enter a valid URL")
            st.stop()

        with st.spinner("Scraping page (this may take 10-20s)..."):
            scraped_data = scrape_model_page(model_url, debug=debug_mode)
            
            if "error" in scraped_data:
                st.error(f"Scraping failed: {scraped_data['error']}")
            else:
                st.success("Scraping successful!")
                # Save to History
                add_history_entry(
                    entry_type="Link Scraper",
                    name=model_url,
                    details="Scraped content successfully",
                    cost=0.0
                )
                
                # Show images
                if scraped_data.get("images"):
                    st.image(scraped_data["images"], width=200, caption=[f"Image {i+1}" for i in range(len(scraped_data["images"]))])
                
                # Show Debug Logs
                if debug_mode and scraped_data.get("debug"):
                    with st.expander("🔍 Scraper Debug Logs"):
                        for log in scraped_data["debug"]:
                            st.write("•", log)

                # Show STL Links
                if scraped_data.get("stl_links"):
                    st.subheader("📥 STL Downloads Found")
                    for link in scraped_data["stl_links"]:
                        st.markdown(f"- [Download STL]({link})")
                else:
                    st.warning("No STL download link found. Upload manually.")

                # AI Analysis of scraped content
                prompt = f"""
                Analyze this scraped 3D model page content:
                
                RAW TEXT:
                {clean_scraped_text(scraped_data['text'])}
                
                TASKS:
                1. Extract Key Print Settings (Layer height, Infill, Walls, Supports) if mentioned.
                2. Summarize the Model Description.
                3. Summarize User Reviews/Sentiment (look for "Comments" or "Reviews" sections in text).
                4. Identify any warnings or common print failures mentioned.
                
                Format nicely with Markdown.
                """
                
                with st.spinner("Analyzing content with Gemini..."):
                    ai_result = ai_analyze(prompt)
                    
                if ai_result["mode"] == "live":
                    st.markdown("### 🧠 AI Model Report")
                    st.markdown(ai_result["analysis"])
                    st.warning("Using mock AI output")
                    st.write(ai_result["analysis"])

    with tab_history:
        st.header("📜 Analysis History")
        history_df = load_history()
        if not history_df.empty:
            st.dataframe(history_df, use_container_width=True)
            if st.button("Clear History"):
                 # Simple clear
                 if os.path.exists("history.csv"):
                     os.remove("history.csv")
                     st.rerun()
        else:
            st.info("No history yet.")

if __name__ == "__main__":
    main()
