"""
Shared utilities for Textract and Landing.ai test runners.

Provides: ground truth loading, PDF→image conversion, skew generation,
Claude judge evaluation, progress tracking, and report generation.
"""
import io
import os
import sys
import json
import time
import random
import logging
import openpyxl
import numpy as np
from datetime import datetime, timezone
from PIL import Image, ImageFilter, ImageEnhance
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Documents"))
from standardize_excels import TEMPLATE_FIELDS, PAGE_MAP

logger = logging.getLogger(__name__)

# ── Ground Truth ──

def load_ground_truth(xlsx_path):
    """Load ground truth from Excel file.

    Returns dict: {field_name: expected_value}
    Uses resolved_value when available, else raw_value.
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    gt = {}
    for row in rows:
        if len(row) < 5:
            continue
        page, section, field, raw_value, resolved_value = row[:5]
        if not field:
            continue
        field = str(field).strip()
        value = str(resolved_value).strip() if resolved_value else (str(raw_value).strip() if raw_value else "")
        if value:
            gt[field] = value
    return gt


def discover_documents(base_dir):
    """Find all PDF/Excel pairs in Quareen/Sadam/Hasan split_output folders.

    Returns list of dicts: [{folder, form_name, pdf_path, xlsx_path}, ...]
    """
    documents = []
    for folder in ["Quareen", "Sadam", "Hasan"]:
        split_dir = os.path.join(base_dir, folder, "split_output")
        if not os.path.isdir(split_dir):
            logger.warning(f"Directory not found: {split_dir}")
            continue

        pdfs = sorted([f for f in os.listdir(split_dir) if f.lower().endswith(".pdf")])
        for pdf_name in pdfs:
            base_name = os.path.splitext(pdf_name)[0]
            xlsx_name = base_name + ".xlsx"
            xlsx_path = os.path.join(split_dir, xlsx_name)
            if not os.path.exists(xlsx_path):
                logger.warning(f"No ground truth for {pdf_name} in {folder}")
                continue
            documents.append({
                "folder": folder,
                "form_name": base_name,
                "pdf_path": os.path.join(split_dir, pdf_name),
                "xlsx_path": xlsx_path,
                "doc_key": f"{folder}/{base_name}",
            })
    return documents


# ── PDF to Image ──

def pdf_to_images(pdf_path):
    """Convert PDF pages to list of PIL Images.

    Uses PyMuPDF (fitz) — no poppler dependency.
    """
    import fitz
    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def image_to_bytes(image, fmt="PNG"):
    """Convert PIL Image to bytes."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


# ── Skew Functions ──

def rotate_180(image_bytes, degrade=False):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.rotate(180, expand=False)
    if degrade:
        tone = Image.new("RGB", img.size, (235, 228, 215))
        img = Image.blend(img, tone, alpha=0.08)
        img = ImageEnhance.Brightness(img).enhance(random.uniform(0.85, 1.15))
        img = ImageEnhance.Contrast(img).enhance(random.uniform(0.85, 1.15))
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0, 0.7)))
        arr = np.array(img, dtype=np.float32)
        arr = np.clip(arr + np.random.normal(0, 8, arr.shape), 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def scan_simulate(image_bytes, preset="light"):
    presets = {
        "light": {"rotation_range": 1.5, "noise": 3, "blur": 0.3,
                  "bright": (0.95, 1.05), "contrast": (0.95, 1.05), "tone": (245, 240, 230)},
        "heavy": {"rotation_range": 5.0, "noise": 15, "blur": 1.2,
                  "bright": (0.75, 1.25), "contrast": (0.75, 1.30), "tone": (225, 215, 200)},
    }
    p = presets[preset]
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tone = Image.new("RGB", img.size, p["tone"])
    img = Image.blend(img, tone, alpha=0.08)
    img = img.rotate(random.uniform(-p["rotation_range"], p["rotation_range"]),
                     expand=False, fillcolor=(255, 255, 255))
    img = ImageEnhance.Brightness(img).enhance(random.uniform(*p["bright"]))
    img = ImageEnhance.Contrast(img).enhance(random.uniform(*p["contrast"]))
    if p["blur"] > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0, p["blur"])))
    if p["noise"] > 0:
        arr = np.array(img, dtype=np.float32)
        arr = np.clip(arr + np.random.normal(0, p["noise"], arr.shape), 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


SKEW_TRANSFORMS = [
    ("180_clean", lambda b: rotate_180(b, degrade=False)),
    ("180_degraded", lambda b: rotate_180(b, degrade=True)),
    ("light_skew", lambda b: scan_simulate(b, "light")),
    ("heavy_skew", lambda b: scan_simulate(b, "heavy")),
]


# ── Judge (Anthropic API Direct) ──

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator assessing the quality of a document extraction system's output.

You are given:
1. The REFERENCE DATA (ground truth field values from the original document)
2. The EXTRACTED FIELDS (output from {system_name})

Your task: For EACH reference field, evaluate:
- extraction_score (0.0-1.0): How well did the system extract this field's value?
  1.0 = the extracted value exactly matches the reference value
  0.5 = partially correct (e.g., minor typo, missing middle name)
  0.0 = the field was not found or is completely wrong
- reasoning: Brief explanation of your score

REFERENCE DATA:
{reference_fields}

EXTRACTED FIELDS:
{extracted_fields_json}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "field_evaluations": [
    {{
      "field_name": "...",
      "reference_value": "...",
      "extracted_value": "value from extraction or empty",
      "extraction_score": 0.0,
      "reasoning": "brief explanation"
    }}
  ],
  "overall_score": 0.0,
  "summary": "1-2 sentence overall assessment"
}}"""


def judge_extraction(reference_data, extracted_fields, system_name, bedrock_client):
    """Evaluate extracted fields against ground truth using Claude on Bedrock as judge.

    Args:
        reference_data: dict {field_name: expected_value}
        extracted_fields: dict {field_name: extracted_value}
        system_name: e.g. "AWS Textract" or "Landing.ai"
        bedrock_client: boto3 bedrock-runtime client

    Returns:
        dict with field_evaluations, overall_score, summary
    """
    # Format reference data
    ref_lines = [f"- {name}: {value}" for name, value in reference_data.items() if value]
    reference_fields_str = "\n".join(ref_lines)

    # Format extracted fields
    extracted_fields_json = json.dumps(extracted_fields, indent=2, default=str)

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        system_name=system_name,
        reference_fields=reference_fields_str,
        extracted_fields_json=extracted_fields_json,
    )

    # Retry with exponential backoff
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = bedrock_client.converse(
                modelId="us.meta.llama4-maverick-17b-instruct-v1:0",
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 8192},
            )
            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])
            response_text = ""
            for block in content_blocks:
                if "text" in block:
                    response_text += block["text"]
            response_text = response_text.strip()
            break
        except Exception as e:
            error_name = type(e).__name__
            if attempt < max_retries - 1 and ("Throttling" in str(e)
                                               or "ServiceUnavailable" in str(e)
                                               or "ModelTimeout" in str(e)):
                wait = (2 ** attempt) * 2
                logger.warning(f"Judge API error ({error_name}), retrying in {wait}s: {e}")
                time.sleep(wait)
                continue
            logger.error(f"Judge API failed: {error_name}: {e}")
            return {
                "field_evaluations": [],
                "overall_score": 0.0,
                "summary": "",
                "error": f"{error_name}: {e}",
            }

    # Parse JSON response
    try:
        # Handle potential markdown code fences
        text = response_text
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        result = json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Judge returned invalid JSON: {response_text[:200]}")
        return {
            "field_evaluations": [],
            "overall_score": 0.0,
            "summary": "",
            "error": f"Invalid JSON response: {response_text[:200]}",
        }

    # Always compute overall score as arithmetic mean of per-field scores
    # (more consistent than the judge's subjective overall score)
    evals = result.get("field_evaluations", [])
    scores = [e.get("extraction_score", 0) for e in evals if e.get("extraction_score") is not None]
    result["judge_overall_score"] = result.get("overall_score", 0.0)  # keep judge's own score
    result["overall_score"] = sum(scores) / len(scores) if scores else 0.0  # use arithmetic mean

    return result


# ── Progress Tracking ──

def load_progress(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"completed": {}, "failed": {}}


def save_progress(path, progress):
    with open(path, "w") as f:
        json.dump(progress, f, indent=2)


# ── Report Generator ──

def generate_report(results_path, system_name):
    """Generate report from aggregated results JSON file."""
    if not os.path.exists(results_path):
        print(f"No results file found at {results_path}")
        return
    with open(results_path, "r") as f:
        results = json.load(f)

    if not results:
        print("No results to report.")
        return

    # Group by skew_type
    grouped = defaultdict(list)
    for r in results:
        grouped[r.get("skew_type", "original")].append(r)

    skew_order = ["original", "light_skew", "heavy_skew", "180_clean", "180_degraded"]
    skew_labels = {
        "original": "Original",
        "light_skew": "Light skew",
        "heavy_skew": "Heavy skew",
        "180_clean": "180° clean",
        "180_degraded": "180° degraded",
    }

    print(f"\n{'=' * 60}")
    print(f"{system_name} RESULTS")
    print(f"{'=' * 60}")

    for skew in skew_order:
        records = grouped.get(skew, [])
        if not records:
            continue

        scores = [r["judge_score"] for r in records if r.get("judge_score") is not None]
        avg = sum(scores) / len(scores) * 100 if scores else 0

        print(f"\n  {skew_labels.get(skew, skew)} ({len(records)} docs): Judge = {avg:.1f}%")
        print(f"  {'Doc':<40} {'Score':>8}")
        print(f"  {'-' * 50}")
        for r in sorted(records, key=lambda x: x.get("judge_score", 0), reverse=True):
            doc = r.get("doc_key", "?")
            score = r.get("judge_score", 0)
            print(f"  {doc:<40} {score * 100:>7.1f}%")

    # Summary
    originals = grouped.get("original", [])
    if originals:
        scores = [r["judge_score"] for r in originals if r.get("judge_score") is not None]
        avg = sum(scores) / len(scores) * 100 if scores else 0
        print(f"\n  OVERALL (originals): {avg:.1f}% across {len(originals)} documents")

    print(f"{'=' * 60}\n")
