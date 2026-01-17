# 1. Base Image
FROM python:3.9-slim

# 2. Set working directory
WORKDIR /app

# 3. Install System Dependencies
# REMOVED: libgconf-2-4 (Broken/Obsolete)
# ADDED: libgbm1, libasound2 (Required for modern Chrome)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libfontconfig1 \
    libxrender1 \
    libxtst6 \
    libnspr4 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy Files
COPY . .

# 5. Install Python Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Install Playwright Browsers
# We run this to be safe, even though we installed chromium above
RUN playwright install chromium

# 7. Expose Port
EXPOSE 8501

# 8. Run App
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
