# OCR Testing App - Debug & Memory Log

## Current Issues (2026-02-10)

### Issue 1: PaddleOCR Returns Empty Text
**Status**: RESOLVED (2026-02-10 ~19:12 UTC)
**Impact**: PaddleOCR test runs complete but all OCR text is empty strings

#### Root Cause:
PaddleOCR 3.4.0's `predict()` returns a `list` of `OCRResult` objects. These `OCRResult` objects **subclass `dict`** — so `isinstance(res, dict)` is `True`. The original code used `getattr(res, 'rec_texts', [])` which hit the default `[]` every time because `getattr` doesn't look up dict keys, only class attributes. The fix uses `res.get('rec_texts', [])` (dict access).

#### Actual result structure (from debug logs):
```
predict() returns: list (len=1)
Result[0]: type=OCRResult (subclasses dict)
Keys: ['input_path', 'page_index', 'doc_preprocessor_res', 'dt_polys',
       'model_settings', 'text_det_params', 'text_type', 'text_rec_score_thresh',
       'return_word_box', 'rec_texts', 'rec_scores', 'rec_polys',
       'vis_fonts', 'textline_orientation_angles', 'rec_boxes']
rec_texts: list of str (45-48 items per document)
rec_scores: list of float (same length)
rec_boxes: list of [x1,y1,x2,y2] (same length)
```

#### What fixed it:
- Strategy 1 in `_extract_from_predict_result()`: `isinstance(res, dict)` → `res.get('rec_texts', [])`
- Also needed `print(flush=True)` + `PYTHONUNBUFFERED=1` for Cloud Run log visibility
- Also needed `ARG CACHE_BUST` in Dockerfile to force Docker layer rebuild

#### Verified working:
- Test run `cb32146a` (doclayout_yolo + paddleocr, 3 docs, completed 19:16:37 UTC)
- 45-48 text detections per document
- Perfect field matches: "Harris" → "Harris" (1.0), "El Paso" → "El Paso" (1.0)
- Region text: "CAUSE NO. El Paso", "STATE OF TEXAS", etc.

### Issue 2: GPU Container Crashes on Cloud Run
**Status**: UNRESOLVED - Parked for now (using CPU)
**Impact**: Transformer-based engines (GOT-OCR, MinerU, TrOCR) are very slow on CPU

#### What we know:
- `nvidia/cuda:12.2.0-runtime-ubuntu22.04` base image crashes silently on Cloud Run
- Zero stdout/stderr — container dies before Python starts
- Multiple revisions tried (00041-00048, v3) all failed identically
- Added `--no-cpu-throttling`, `--execution-environment=gen2` — didn't help
- Health check is fine (added `GET /` root endpoint)

#### What we haven't tried:
- Different base image: `pytorch/pytorch:2.x-cuda12.x-cudnn8-runtime`
  - This is pre-built with Python, PyTorch, CUDA — more likely to work on Cloud Run
  - Would eliminate the need for separate CUDA/Python installation
- `nvidia/cuda:12.4.x` or newer CUDA versions
- Google's Deep Learning Container images (e.g., `gcr.io/deeplearning-platform-release/pytorch-gpu`)

#### Cloud Run GPU requirements:
- `--gpu 1 --gpu-type nvidia-l4`
- `--no-cpu-throttling` (required for GPU)
- `--execution-environment gen2` (required for GPU)
- `--cpu 4 --memory 16Gi` minimum

### Issue 3: Cloud Run Autoscaling Kills Background Tasks
**Status**: MITIGATED (2026-02-10) - Auto-detection + manual cancel added
**Impact**: Long-running OCR tasks can be killed when instance is recycled

#### What we know:
- FastAPI BackgroundTasks die when Cloud Run recycles the instance
- Instance was recycled at 17:43:52 while PaddleOCR was processing
- Instance was recycled at 20:38:54 while Surya was at 35% on document 10
- Batch job `e4091aca` stuck at 1/5 combinations (surya stuck, paddleocr/tesseract/trocr never started)
- Cloud Run `--timeout 600` (10min) should help, but autoscaling can still kill
- Background tasks are sequential within a batch — if one gets killed, remaining combos never start

#### Mitigation implemented:
1. **Heartbeat tracking**: Every status update writes `last_heartbeat` timestamp to Firestore
2. **Stale detection**: `list_test_runs()` and `list_batch_jobs()` auto-mark entries as "failed" if they've been "running" with no heartbeat for >10 minutes (configurable `STALE_THRESHOLD`)
3. **Batch job cancel endpoint**: `POST /tests/batch-jobs/{id}/cancel` — cancels the batch job AND all its child test runs
4. **Cancel buttons in UI**: Both individual test runs and batch jobs have cancel buttons in the progress bars

---

## Deployment Info
- **Backend**: `ocr-app-backend-debug-v4` (CPU, 4 vCPU, 16Gi RAM) — 100% traffic
- **Frontend**: `ocr-app-frontend-00024-2h6`
- **Region**: us-central1
- **Project**: ocr-testing-app
- **Storage bucket**: ocr-testing-app-ocr-forms

## What's Working
- All 7 OCR engines load and initialize (PaddleOCR, EasyOCR, Surya, Tesseract, TrOCR, GOT-OCR, MinerU)
- **PaddleOCR text extraction WORKS** (fixed 2026-02-10)
- **EasyOCR text extraction WORKS** (test `3ee7dbd4` completed 10/10 docs in ~3 min)
- DocLayout-YOLO layout detection works correctly
- Layout caching in Firestore works
- Image caching in memory works
- Batch combination jobs work (sequential — auto-detects stale runs if killed)
- Stale test/batch job auto-detection (>10 min without heartbeat → marked failed)
- Cancel buttons for individual tests and batch jobs
- Frontend multi-select UI works
- Duration tracking works
- Verify page OCR dropdown works
- Health check endpoint works (`GET /`)

## Architecture
- Backend: FastAPI + Python 3.11 on Cloud Run
- Frontend: React + Vite on Cloud Run
- Database: Firestore
- Storage: Google Cloud Storage
- OCR engines: PaddleOCR 3.x (PP-OCRv5), EasyOCR, Surya, Tesseract, TrOCR, GOT-OCR 2.0, MinerU 2.5
- Layout detection: DocLayout-YOLO
