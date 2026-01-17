FROM python:3.9-slim

WORKDIR /app

# Install Chrome dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# Port for Streamlit
EXPOSE 8501

# Run the app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
