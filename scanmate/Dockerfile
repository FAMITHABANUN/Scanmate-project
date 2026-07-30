FROM python:3.11-slim

# Tesseract is the free, open-source OCR engine ScanMate uses.
# fonts-noto/fonts-noto-cjk give the PDF/image export real glyph coverage
# for Tamil, Hindi and other Indic scripts, Arabic, Chinese/Japanese/Korean,
# etc. - without them, non-Latin scans still work but fall back to a plain
# text note in exports (see utils/export.py).
RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr fonts-noto fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p instance static/uploads

ENV PORT=10000
EXPOSE 10000

CMD gunicorn --bind 0.0.0.0:$PORT app:app