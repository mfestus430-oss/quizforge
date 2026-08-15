FROM python:3.12-slim

# Tesseract OCR is needed for reading text from uploaded images
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Render sets $PORT automatically; default to 10000 for local runs
ENV PORT=10000
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 300 app:app
