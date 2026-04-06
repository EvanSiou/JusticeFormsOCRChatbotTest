# Plan: Performance Improvements, Verify Dropdown, Batch Combination Jobs

## Context
Three improvements to the OCR testing app:
1. **Performance**: PaddleOCR takes 1+ hours because every traditional OCR engine (PaddleOCR, EasyOCR, Surya, Tesseract) re-runs its own internal text detection on each cropped region, even though layout detection already found the regions. This is redundant work — and with 10-15 regions per document at 2-10s each, it adds up massively. Plus: layout detection re-runs unnecessarily across test runs, and images re-download from GCS each time.
2. **Verify UX**: On the typed/synthetic verify page, users can only see the best fuzzy-matched value. Adding a dropdown of all OCR text values lets them select the correct one if it was extracted but matched wrong.
3. **Batch combos**: Currently users must manually run each layout+OCR combination one at a time. A batch job feature lets them multi-select libraries and run all combinations automatically.

Implementation order: Feature 1 → Feature 2 → Feature 3

---

## Feature 1: Performance Improvements

### Problem Analysis

Every traditional OCR engine does its own text detection internally, which is **redundant** when layout detection already identified the regions:

| Engine | What happens per-region | Time/region | Redundant detection? |
|---|---|---|---|
| **PaddleOCR** | `predict()` runs full det+rec+cls pipeline | ~5-10s | YES |
| **EasyOCR** | `readtext()` runs detection+recognition | ~2-3s | YES |
| **Surya OCR** | `RecognitionPredictor` runs detection+recognition | ~2-3s | YES |
| **Tesseract** | `image_to_data()` runs internal line detection | ~0.5-1s | YES (but fast) |
| **TrOCR** | Recognition only (expects single lines) | ~1-2s/line | No — already rec-only |
| **GOT-OCR** | Full-page VLM, single pass | N/A | Already optimized |
| **MinerU** | Full-page VLM, single pass | N/A | Already optimized |

With 15 regions per document: PaddleOCR = ~75-150s/doc, EasyOCR = ~30-45s/doc, Surya = ~30-45s/doc.

### 1A. Full-image single-pass for PaddleOCR, EasyOCR, and Surya

**Files**: [paddleocr_engine.py](ocr-testing-app/backend/app/processing/ocr/paddleocr_engine.py), [easyocr_engine.py](ocr-testing-app/backend/app/processing/ocr/easyocr_engine.py), [surya_ocr.py](ocr-testing-app/backend/app/processing/ocr/surya_ocr.py), [base.py](ocr-testing-app/backend/app/processing/ocr/base.py)

**Strategy**: Instead of cropping each region and running the full OCR pipeline per crop, run OCR once on the full document image, then map the detected text back to layout regions by bounding box overlap.

**Add to base.py** — shared `_bbox_overlap()` helper:
```python
@staticmethod
def _bbox_contains(outer, inner_center_x, inner_center_y):
    """Check if a point falls within a bounding box."""
    return (outer["x1"] <= inner_center_x <= outer["x2"] and
            outer["y1"] <= inner_center_y <= outer["y2"])
```

**PaddleOCR** — override `extract_text()`:
- Run `ocr.predict(full_image)` once on the full document
- For each detected text line, compute its center point
- Map it to the layout region whose bbox contains that center
- Build per-region `OCRResult` objects from the mapped lines
- **Reduces from 15 calls x 5-10s = 75-150s → 1 call x 10-15s**

**EasyOCR** — override `extract_text()`:
- Run `reader.readtext(full_image)` once
- Map each detection to its containing layout region by bbox center
- **Reduces from 15 calls x 2-3s = 30-45s → 1 call x 5-8s**

**Surya OCR** — override `extract_text()`:
- Surya already supports batch processing: `predictor([image], bboxes=[list_of_bboxes])`
- Instead of calling per-region, pass ALL region bboxes in a single call
- Surya will recognize text within each provided bbox
- **Reduces from 15 calls x 2-3s = 30-45s → 1 batch call x 5-8s**

**Tesseract** — leave as-is. At 0.5-1s/region, the per-region approach is acceptable and Tesseract's `image_to_data()` is fast. Not worth the complexity of bbox remapping.

### 1B. Layout detection caching in Firestore

**Files**: [ocr_pipeline.py](ocr-testing-app/backend/app/services/ocr_pipeline.py), [firestore.py](ocr-testing-app/backend/app/services/firestore.py)

**firestore.py**: New `layout_cache` Firestore collection keyed by SHA-256 of `storage_path::layout_library`
- `get_cached_layout(cache_key)` → cached dict or None
- `set_cached_layout(cache_key, layout_data)` → stores layout_results

**ocr_pipeline.py**: In `process_document()`, before detection:
- Check cache → if hit, reconstruct `Region` list from cached dict
- If miss, run detection and cache results
- **Saves ~5s/doc on 2nd+ run with same layout library** — huge for batch combo jobs (Feature 3)

### 1C. Image download caching (in-memory per batch)

**File**: [ocr_pipeline.py](ocr-testing-app/backend/app/services/ocr_pipeline.py)

Add optional `image_cache` dict parameter to `process_batch()` and `process_document()`. When running batch combo jobs (Feature 3), a shared cache dict is passed so images download once across all combos. ~5-25MB memory for 10-50 images.

### 1D. GPU deployment option (recommended — fits $100/month budget)

**Files**: [Dockerfile.gpu](ocr-testing-app/backend/Dockerfile.gpu) (already exists), [cloudbuild.yaml](ocr-testing-app/cloudbuild.yaml) or [cloudbuild-gpu.yaml](ocr-testing-app/backend/cloudbuild-gpu.yaml)

**Cost analysis** (NVIDIA L4 on Cloud Run @ $0.67/hour):
- Cloud Run GPU **scales to zero** — you only pay for actual processing time
- If actual GPU processing is 1-2 hours/day → **$20-40/month**
- If 3 hours/day → **$60/month**
- Even at 4 hours/day → **$80/month** (well within $100/month budget)
- CPU costs (4 vCPU, 8Gi) are negligible on top of GPU

**GPU speedup estimates**:
- PaddleOCR: 5-10x faster inference on GPU (CUDA accelerated Paddle)
- EasyOCR: 3-5x faster (PyTorch CUDA backend)
- GOT-OCR/MinerU: 5-20x faster (transformers models with float16 on GPU)
- DocLayout-YOLO: 3-5x faster detection on GPU
- TrOCR: 5-10x faster (transformer model, batch inference)

**Approach**: Deploy the GPU Dockerfile as a separate Cloud Run service (e.g., `ocr-app-backend-gpu`) alongside the CPU service. The frontend can toggle which backend to use, or the GPU service can be the default with CPU as fallback.

**Alternatively**: Replace the CPU deployment with GPU. The GPU Dockerfile already exists and all engines already check for `torch.cuda.is_available()`. The code change is minimal — update `cloudbuild.yaml` to use the GPU Dockerfile and add `--gpu 1 --gpu-type nvidia-l4 --cpu 4 --memory 16Gi` to the deploy step.

### Combined performance impact

| Scenario | Before | After (CPU optimized) | After (GPU) |
|---|---|---|---|
| PaddleOCR 20 docs | ~25-50 min | ~4-5 min | ~1-2 min |
| EasyOCR 20 docs | ~10-15 min | ~2-3 min | ~1 min |
| Surya 20 docs | ~10-15 min | ~2-3 min | ~1 min |
| 2nd run same layout | +5s/doc | 0s (cached) | 0s (cached) |
| Batch combo (4 combos) | 4x download time | 1x download (cached) | 1x download (cached) |

---

## Feature 2: OCR Values Dropdown on Verify Page

**Files to modify:**
- [VerifyPage.jsx](ocr-testing-app/frontend/src/pages/VerifyPage.jsx) - Frontend only

### Collect all OCR text values
- After `ocrByRegionId` construction (~line 203), compute `allOcrTexts`:
  - Gather unique text from `doc.ocr_results.regions[].full_text`, `doc.ocr_results.regions[].lines[].text`, and `doc.ocr_results.text_regions[].text`
  - Deduplicate with a Set, sort alphabetically

### Add dropdown to each synthetic field
- In the extracted fields map (lines 434-503), between the Expected/Extracted grid and the Correct/Incorrect radio buttons, add a `<select>` dropdown
- Options: all items from `allOcrTexts`
- On selection: calls existing `handleCorrectedValue(field.field_name, value)` which auto-sets status to "corrected" and populates the corrected_value input
- Truncate long text in option labels (80 chars)

**No backend changes needed** — `ocr_results` with full region data is already returned by the verification endpoint.

---

## Feature 3: Batch Combination Jobs

**Files to modify:**
- [test_run.py](ocr-testing-app/backend/app/models/test_run.py) - New models
- [firestore.py](ocr-testing-app/backend/app/services/firestore.py) - Batch job CRUD
- [tests.py](ocr-testing-app/backend/app/routers/tests.py) - New endpoints + background task
- [api.js](ocr-testing-app/frontend/src/services/api.js) - New API methods
- [RunTestsPage.jsx](ocr-testing-app/frontend/src/pages/RunTestsPage.jsx) - Multi-select UI

### test_run.py - New models
- `BatchJobInDB`: id, batch_ids, layout_libraries[], ocr_libraries[], started_by, status, test_run_ids[], total_combinations, completed_combinations
- `BatchJobResponse`, `BatchJobListResponse`, `RunBatchJobRequest`
- Add `batch_job_id: Optional[str] = None` to `TestRunInDB` to link child runs to parent job

### firestore.py - Batch job CRUD
- New `batch_jobs` Firestore collection
- `create_batch_job()`, `get_batch_job_by_id()`, `update_batch_job()`, `list_batch_jobs()`
- Update `create_test_run()` to accept optional `batch_job_id`

### tests.py - New endpoints and background task
- **Route ordering**: Place new endpoints BEFORE `/{test_run_id}` to avoid catch-all conflict
- `POST /tests/batch-job` → validates batches/libraries, creates BatchJob, launches background task
- `GET /tests/batch-jobs` → list all batch jobs
- `GET /tests/batch-jobs/{job_id}` → get single batch job status
- `run_batch_job_background()`:
  - Builds all (layout, ocr) combinations (VLM engines skip layout selection)
  - For each combo: creates a test_run record, then calls `run_test_background()` directly (sequential)
  - Updates `completed_combinations` after each combo finishes
  - Individual combo failures don't stop the overall job
  - Passes shared `image_cache={}` across all combos (Feature 1C synergy)
  - Layout cache (Feature 1B) auto-benefits: 2nd OCR engine with same layout reuses cached regions

### api.js - New API methods
- `testsAPI.runBatchJob(batchIds, layoutLibraries, ocrLibraries)`
- `testsAPI.listBatchJobs()`
- `testsAPI.getBatchJob(id)`

### RunTestsPage.jsx - Multi-select UI
- Replace single-select dropdowns with checkbox lists for both layout and OCR libraries
- Show combination count: "This will run N combination(s)"
- VLM engines tagged with `(VLM)` label; auto-excluded from layout combinations
- Run button logic: if 1 combo → use existing `testsAPI.run()`; if multiple → use `testsAPI.runBatchJob()`
- Add batch job polling (3s interval) with purple progress bar showing `completed/total combinations`
- In Previous Test Runs list: add `batch` badge on runs that belong to a batch job
- Individual test runs still appear in the list and can be viewed/verified normally

---

## Verification

1. **Feature 1A**: Run PaddleOCR and EasyOCR on a batch. Should complete in ~4-5min for 20 docs instead of 25+ min.
2. **Feature 1B**: Run same document through same layout library twice. Second run should skip detection. Check `layout_cache` in Firestore.
3. **Feature 1C/1D**: Run batch combo job — images download once, GPU accelerates all engines.
4. **Feature 2**: Open verify page for typed test run. Each field shows dropdown of all OCR text. Selecting a value auto-marks as corrected.
5. **Feature 3**: Select 2 layout libs + 2 OCR engines, run. Creates batch job with 4 combos. Progress bar tracks completion. Each finished combo viewable/verifiable individually.
6. **Deploy**: `gcloud builds submit --config=cloudbuild.yaml .` from `ocr-testing-app/`
