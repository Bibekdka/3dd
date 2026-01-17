# 1. Base Image
FROM python:3.11-slim

# 2. Set working directory
WORKDIR /app

# 3. Install System Dependencies (Required for Playwright/Chrome)
# We install these BEFORE python requirements to cache them
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy Files
COPY . .

# 5. Install Python Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Install Playwright Browsers (The Critical Step)
RUN playwright install chromium
RUN playwright install-deps

# 7. Expose Streamlit Port
EXPOSE 8501

# 8. Run the App
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
