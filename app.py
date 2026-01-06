import streamlit as st
import trimesh
import numpy as np
import os
import tempfile
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from playwright.sync_api import sync_playwright
import time

# Load environment variables
load_dotenv()
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    # We defer error showing to main to utilize st.error
    pass

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

def scrape_model_page(url):
    """
    Scrapes a generic 3D model page for content using Playwright.
    Returns text content and a list of image URLs.
    """
    try:
        with sync_playwright() as p:
            # Launch with headless=True
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait a bit for dynamic content / CF
            time.sleep(5)
            
            # Domain specific tweaks
            if "makerworld.com" in url:
                # Try to click comments/reviews tab
                try:
                    page.locator(".js-comment-and-rating").click(timeout=3000)
                    time.sleep(2)
                except: pass
            elif "printables.com" in url:
                try:
                     # Printables often has "Comments" tab
                    page.get_by_text("Comments").click(timeout=3000)
                    time.sleep(2)
                except: pass

            # Extract full text
            text_content = page.locator("body").inner_text()
            
            # Extract images (Naive: get all large images)
            # Filter for likely model images
            images = page.locator("img").evaluate_all("""
                imgs => imgs.filter(img => img.width > 300 && img.height > 300).map(img => img.src)
            """)
            
            browser.close()
            
            return {
                "text": text_content[:50000], # Limit content for token limits
                "images": list(set(images))[:5] # Top 5 unique images
            }
            
    except Exception as e:
        return {"error": str(e)}

def ai_analyze(prompt_text):
    """
    Analyzes the print settings using Gemini API.
    Returns a dict with 'mode' ('live' or 'mock') and 'analysis' (text).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        return {
            "mode": "mock",
            "analysis": "AI key not found. Mock recommendation: Increase infill for better strength."
        }
    
    try:
        # Use a model that supports generateContent
        model = genai.GenerativeModel('gemini-1.5-flash') 
        response = model.generate_content(prompt_text)
        return {
            "mode": "live",
            "analysis": response.text
        }
    except Exception as e:
        return {
            "mode": "mock",
            "analysis": f"AI Error: {str(e)}. Mock advice: Check mesh integrity."
        }

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

def analyze_stl(file_path, density, cost_per_kg, infill, walls):
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
        
        return {
            "Raw Volume (cm3)": round(volume_cm3, 2),
            "Effective Volume (cm3)": round(effective_volume, 2),
            "Weight (g)": round(weight_g, 2),
            "Cost ($)": round(cost, 2),
            "Vertices": len(mesh.vertices),
            "Faces": len(mesh.faces),
            "Watertight": mesh.is_watertight
        }
    except Exception as e:
        return None

def main():
    st.set_page_config(page_title="3D Slicer Volume Estimator", page_icon="🧊")

    st.title("🧊 3D Slicer Volume Estimator")
    
    # Sidebar for API Status
    with st.sidebar:
        if os.getenv("GEMINI_API_KEY"):
            st.success("Gemini API Key Detected", icon="✅")
        else:
            st.warning("Gemini API Key Missing", icon="⚠️")

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
                    analysis = analyze_stl(tmp_path, density, cost_per_kg, infill, walls)
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
        
        c1, c2 = st.columns(2)
        c1.metric("Total Batch Cost", f"${total_cost:.2f}")
        c2.metric("Total Batch Weight", f"{total_weight:.1f} g")

        # Batch features (AI + PDF)
        st.divider()
        
        col_actions1, col_actions2 = st.columns(2)
        
        with col_actions1:
            if st.button("🧠 Analyze Batch with AI"):
                with st.spinner("Consulting Gemini..."):
                    summary_text = f"""
                    Batch Analysis of {len(batch_results)} files:
                    Total Cost: ${total_cost:.2f}
                    Total Weight: {total_weight:.1f}g
                    
                    Files Overview:
                    {df.to_string(index=False)}
                    
                    Provide a summary recommendation for this production batch.
                    """
                    ai_result = ai_analyze(summary_text)
                    if ai_result["mode"] == "live":
                        st.success("Batch AI Analysis")
                        st.write(ai_result["analysis"])
                    else:
                        st.warning("Using mock AI output")
                        st.json(ai_result)

        with col_actions2:
            # Generate Text/PDF report for batch
            # For simplicity, sending a summary string to the PDF function we already have
            # Ideally we'd modify export_pdf_report to handle tables nicely, but let's send a summary dict
            batch_report_data = {
                "Report Type": "Batch Analysis",
                "File Count": len(batch_results),
                "Total Cost": f"${total_cost:.2f}",
                "Total Weight": f"{total_weight:.1f} g",
                "Infill": f"{infill}%",
                "Density": f"{density} g/cm3",
            }
            # Append per-file details to keys? Or just simplified
            # Let's keep it simple for now as per user request to just "Export PDF"
            pdf_path = export_pdf_report(batch_report_data)
            
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📄 Download Batch Report",
                    data=f,
                    file_name="batch_report.pdf",
                    mime="application/pdf"
                )

# Load environment variables
load_dotenv()
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    # We defer error showing to main to utilize st.error
    pass

def export_pdf_report(data):
    path = "print_report.pdf"
    c = canvas.Canvas(path, pagesize=A4)
    y = 800

    c.setFont("Helvetica", 14)
    c.drawString(40, 820, "3D Slicer Volume Estimator Report")
    
    c.setFont("Helvetica", 11)

    for key, value in data.items():
        c.drawString(40, y, f"{key}: {value}")
        y -= 25 # Increased spacing slightly
        if y < 50:
            c.showPage()
            y = 800

    c.save()
    return path

def ai_analyze(prompt_text):
    """
    Analyzes the print settings using Gemini API.
    Returns a dict with 'mode' ('live' or 'mock') and 'analysis' (text).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        return {
            "mode": "mock",
            "analysis": "AI key not found. Mock recommendation: Increase infill for better strength."
        }
    
    try:
        # Use a model that supports generateContent
        # We try a few common ones or default
        model = genai.GenerativeModel('gemini-1.5-flash') 
        response = model.generate_content(prompt_text)
        return {
            "mode": "live",
            "analysis": response.text
        }
    except Exception as e:
        return {
            "mode": "mock",
            "analysis": f"AI Error: {str(e)}. Mock advice: Check mesh integrity."
        }

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

def save_uploaded_file(uploaded_file):
    try:
        suffix = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            return tmp_file.name
    except Exception as e:
        st.error(f"Error saving file: {e}")
        return None

def main():
    st.set_page_config(page_title="3D Slicer Volume Estimator", page_icon="🧊")

    st.title("🧊 3D Slicer Volume Estimator")
    
    # Sidebar for API Status
    with st.sidebar:
        if os.getenv("GEMINI_API_KEY"):
            st.success("Gemini API Key Detected", icon="✅")
        else:
            st.warning("Gemini API Key Missing", icon="⚠️")

    st.markdown("""
    Upload an STL file to calculate its volume and estimate the *effective* volume 
    based on your slicer settings (Wall Thickness vs Infill).
    """)

    uploaded_file = st.file_uploader("Upload 3D Model (STL)", type=["stl"])

    if uploaded_file is not None:
        file_path = save_uploaded_file(uploaded_file)
        
        if file_path:
            try:
                # Load mesh
                mesh = trimesh.load(file_path)
                
                # Cleanup temporal file
                os.remove(file_path)

                if not mesh.is_watertight:
                    st.warning("⚠️ The mesh is not watertight. Volume calculations might be inaccurate.")
                
                # Calculate raw volume
                # trimesh volume is usually in cubic units of the mesh (often mm^3)
                volume_raw = mesh.volume
                
                # Assume units are mm, convert to cm^3 (1 cm^3 = 1000 mm^3)
                # If mesh is already in cm (unlikely for STL), this would be off, but mm is standard.
                volume_cm3 = volume_raw / 1000.0

                st.divider()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Model Stats")
                    st.metric("Raw Volume", f"{volume_cm3:.2f} cm³")
                    st.text(f"Vertices: {len(mesh.vertices)}")
                    st.text(f"Faces: {len(mesh.faces)}")

                with col2:
                    st.subheader("Slicer Settings")
                    infill = st.slider("Infill Percentage (%)", 0, 100, 20)
                    walls = st.slider("Wall/Shell Percentage (%)", 0, 100, 25)

                # Simple cost estimator (e.g. PLA density ~1.24 g/cm3)
                density = 1.24 # g/cm3

                # Calculate effective volume using slider values
                effective_volume = slicer_volume_adjustment(
                    volume_cm3,
                    infill_percent=infill,
                    wall_percent=walls
                )
                
                weight_g = effective_volume * density

                st.divider()
                st.subheader("Estimation Results")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Effective Volume", f"{effective_volume:.2f} cm³", 
                          delta=f"{effective_volume - volume_cm3:.2f} cm³",
                          delta_color="inverse") # Less volume is usually better/cheaper, but here we show difference
                
                cost_per_kg = 20.0 # USD
                cost = (weight_g / 1000) * cost_per_kg
                
                c2.metric("Estimated Weight (PLA)", f"{weight_g:.1f} g")
                c3.metric("Estimated Material Cost", f"${cost:.2f}")

                st.divider()
                st.subheader("🧠 AI Print Recommendations")
                
                # Construct context for AI
                combined_text = f"""
                Analyze this 3D print job:
                - Raw Volume: {volume_cm3:.2f} cm3
                - Selected Infill: {infill}%
                - Selected Wall Thickness: {walls}%
                - Effective Volume: {effective_volume:.2f} cm3
                - Estimated Weight: {weight_g:.1f} g
                
                Give specific recommendations on:
                1. Whether the infill/wall ratio is appropriate for a standard part.
                2. Potential print time or structural concerns.
                3. Ways to optimize cost without losing too much strength.
                Keep it concise (bullet points).
                """

                # Add a button so it doesn't run on every slider change automatically (optional, but good UX)
                # Or just run it if the user asks. User code implies direct run, but let's put it behind a button/expander or just run it.
                # Given 'combined_text' variable in user request, I'll run it directly or maybe check if 'ai_result' is needed.
                # Let's add a button to trigger it to save API calls.
                
                if st.button("Generate AI Assessment"):
                    with st.spinner("Consulting Gemini..."):
                        ai_result = ai_analyze(combined_text)

                    if ai_result["mode"] == "live":
                        st.success("Gemini AI Analysis")
                        st.write(ai_result["analysis"])
                    else:
                        st.warning("Using mock AI output (Check API Key or Connection)")
                        st.json(ai_result)

                st.divider()
                
                # Prepare data for report
                report_data = {
                    "File Name": uploaded_file.name,
                    "Raw Volume": f"{volume_cm3:.2f} cm3",
                    "Infill Percentage": f"{infill}%",
                    "Wall Percentage": f"{walls}%",
                    "Effective Volume": f"{effective_volume:.2f} cm3",
                    "Estimated Weight (PLA)": f"{weight_g:.1f} g",
                    "Estimated Material Cost": f"${cost:.2f}",
                }
                
                # We use a direct download button for better UX in Streamlit
                # Generate PDF immediately so it's ready for download
                pdf_path = export_pdf_report(report_data)
                
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="📄 Download PDF Report",
                        data=f,
                        file_name="print_report.pdf",
                        mime="application/pdf"
                    )

            except Exception as e:
                st.error(f"Error processing mesh: {e}")

    # Link Parser Section
    st.divider()
    st.header("🔗 Link Parser (Universal Scraper)")
    st.markdown("Supports MakerWorld, Printables, Thangs, Thingiverse, etc. Pasting a link scrapes images, settings, and reviews for AI analysis.")
    
    model_url = st.text_input("Paste 3D Model URL")
    
    if st.button("🚀 Scrape & Analyze"):
        if model_url:
            with st.spinner("Scraping page (this may take 10-20s)..."):
                scraped_data = scrape_model_page(model_url)
                
            if "error" in scraped_data:
                st.error(f"Scraping failed: {scraped_data['error']}")
            else:
                st.success("Scraping successful!")
                
                # Show images
                if scraped_data.get("images"):
                    st.image(scraped_data["images"], width=200, caption=[f"Image {i+1}" for i in range(len(scraped_data["images"]))])
                
                # AI Analysis of scraped content
                with st.spinner("Analyzing content with Gemini..."):
                    prompt = f"""
                    Analyze this scraped 3D model page content:
                    
                    RAW TEXT:
                    {scraped_data['text']}
                    
                    TASKS:
                    1. Extract Key Print Settings (Layer height, Infill, Walls, Supports) if mentioned.
                    2. Summarize the Model Description.
                    3. Summarize User Reviews/Sentiment (look for "Comments" or "Reviews" sections in text).
                    4. Identify any warnings or common print failures mentioned.
                    
                    Format nicely with Markdown.
                    """
                    
                    ai_result = ai_analyze(prompt)
                    
                    if ai_result["mode"] == "live":
                        st.markdown("### 🧠 AI Model Report")
                        st.write(ai_result["analysis"])
                    else:
                        st.warning("Using mock AI output")
                        st.write(ai_result["analysis"])
        else:
            st.warning("Please enter a URL")

if __name__ == "__main__":
    main()
else:
    # Ensure it runs when imported by AppTest if necessary, 
    # OR just call main() unconditionally at the end of script which is standard for streamlit scripts
    main()
