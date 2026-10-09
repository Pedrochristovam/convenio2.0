# Backend do Convênio 2.0 (FastAPI) com OCR (Tesseract) e conversão DOCX -> PDF (LibreOffice)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TESSERACT_LANG=por+eng

# Carlito e Caladea têm as mesmas métricas de Calibri e Cambria: o PDF da AD não desalinha
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
        libreoffice-writer-nogui \
        fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY start_backend.py .

CMD ["python", "start_backend.py"]
