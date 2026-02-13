FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OCR libraries (includes tesseract-ocr)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    gcc \
    g++ \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (full OCR/ML stack)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download model weights during build (avoids downloads at runtime)

# DocLayout-YOLO layout detection model
RUN python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='juliozhao/DocLayout-YOLO-DocStructBench', filename='doclayout_yolo_docstructbench_imgsz1024.pt')"

# PaddleOCR models (PP-OCRv5 det + rec + textline orientation)
RUN python -c "import os; os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'; from paddleocr import PaddleOCR; PaddleOCR(lang='en', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True, device='cpu', enable_mkldnn=False)"

# EasyOCR English models (detector + recognizer)
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False, verbose=False)"

# Surya OCR models (Foundation + Recognition predictors + Layout predictor)
RUN python -c "from surya.recognition import RecognitionPredictor; from surya.foundation import FoundationPredictor; fp = FoundationPredictor(); RecognitionPredictor(fp)"
RUN python -c "from surya.foundation import FoundationPredictor; from surya.layout import LayoutPredictor; from surya.settings import settings; LayoutPredictor(FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT))"

# TrOCR handwritten model (~330MB)
RUN python -c "from transformers import TrOCRProcessor, VisionEncoderDecoderModel; TrOCRProcessor.from_pretrained('microsoft/trocr-base-handwritten'); VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-handwritten')"

# GOT-OCR2.0 model (~580M params)
RUN python -c "from transformers import AutoProcessor, AutoModelForImageTextToText; AutoProcessor.from_pretrained('stepfun-ai/GOT-OCR-2.0-hf', use_fast=True); AutoModelForImageTextToText.from_pretrained('stepfun-ai/GOT-OCR-2.0-hf')"

# MinerU model (~1.2B params based on Qwen2VL)
RUN python -c "from transformers import AutoProcessor, Qwen2VLForConditionalGeneration; AutoProcessor.from_pretrained('opendatalab/MinerU2.5-2509-1.2B', use_fast=True); Qwen2VLForConditionalGeneration.from_pretrained('opendatalab/MinerU2.5-2509-1.2B')"

# Force offline mode so models load from cache without hitting network
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Ensure Python output is not buffered (critical for Cloud Run logging)
ENV PYTHONUNBUFFERED=1

# Cache buster — change to force rebuild of code layer
ARG CACHE_BUST=20260212v3

# Copy application code
COPY . .

# Cloud Run uses PORT env var (defaults to 8080)
EXPOSE 8080

# Run with uvicorn on the PORT provided by Cloud Run
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
