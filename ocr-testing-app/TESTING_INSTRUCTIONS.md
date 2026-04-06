# OCR Testing App - Team Testing Instructions

## Quick Start

1. Go to: https://ocr-app-frontend-206256614025.us-central1.run.app
2. Login with your credentials (ask Leo for account creation)
3. Filter by your name using the User dropdown to see only your work

---

## Testing Plan

Follow this prescribed order to get familiar with the system:

### Day 1: Learn with Synthetic Forms

**Goal**: Understand the app workflow using generated data.

#### Step 1: Generate Synthetic Data
1. Go to **Synthetic Data** page
2. Click **Generate New Batch**
3. Select form: `OP-SWO-DOCKET.PNG`
4. Set copies: **5** (small batch for learning)
5. Click **Generate**
6. Wait for batch to appear in the list

#### Step 2: Run Your First Test
1. Go to **Run Tests** page
2. Select your batch (look for your name)
3. Choose libraries:
   - **Layout**: `doclayout_yolo` (recommended - fastest and most accurate)
   - **OCR**: `easyocr` (good baseline)
4. Click **Run Tests**
5. Watch the progress bar - should complete in ~1 minute

#### Step 3: Review Results
1. Click **View Results** when test completes
2. Observe:
   - Overall accuracy percentage
   - Per-field breakdown
   - Image viewer with detected regions
3. Click on individual documents to see detailed results

### Day 2: Compare OCR Libraries

**Goal**: Understand how different OCR engines perform.

Run tests on the SAME batch with different OCR engines:

| Test | Layout | OCR | Expected Speed | Notes |
|------|--------|-----|----------------|-------|
| 1 | doclayout_yolo | easyocr | Fast | Good baseline |
| 2 | doclayout_yolo | paddleocr | Fast | Often better on printed text |
| 3 | doclayout_yolo | tesseract | Fast | Classic OCR, good on clean scans |
| 4 | doclayout_yolo | surya | Medium | Good on mixed layouts |
| 5 | doclayout_yolo | trocr | Slow | Handwriting specialist |

Compare results in the Results page to see which performs best.

### Day 3: Test VLM Engines (Vision Language Models)

**Goal**: Test the most advanced OCR engines.

VLM engines (`got_ocr` and `mineru`) are special - they:
- Process the FULL PAGE in one pass
- Don't need layout detection (dropdown is hidden)
- Are slower but can handle complex documents

| Test | OCR | Notes |
|------|-----|-------|
| 1 | got_ocr | GOT-OCR2.0 - 580M parameter VLM |
| 2 | mineru | MinerU - 1.2B parameter VLM based on Qwen2VL |

When you select `got_ocr` or `mineru`:
- The Layout dropdown disappears (not needed)
- A message explains why
- Tests take longer (~2-3 min per document on CPU)

### Day 4: Handwritten Forms

**Goal**: Test OCR on real handwritten documents.

#### Upload Handwritten Batch
1. Go to **Synthetic Data** page
2. Click **Upload Handwritten Batch**
3. Select your scanned handwritten forms
4. These bypass synthetic generation - just creates distortion copies

#### Run Handwritten Tests
1. Go to **Run Tests**
2. Select your handwritten batch (shows "Handwritten" badge)
3. Note: Layout detection is disabled for handwritten batches
4. Try different OCR engines:
   - `trocr` - Designed for handwriting
   - `got_ocr` - VLM that handles mixed content
   - `easyocr` - General purpose

#### Verify Handwritten Results
1. Go to **Verify** page
2. Find your handwritten test run
3. Mark which text regions are actual handwriting (important)
4. This helps calculate meaningful accuracy

---

## Library Reference

### Layout Detectors
| Name | Speed | Best For |
|------|-------|----------|
| `doclayout_yolo` | Fast | General documents, forms |
| `doctr` | Medium | Dense text documents |
| `surya` | Medium | Mixed layouts |

### OCR Engines
| Name | Speed | Best For | Notes |
|------|-------|----------|-------|
| `easyocr` | Fast | General text | Good baseline |
| `paddleocr` | Fast | Printed text | Often highest accuracy on forms |
| `tesseract` | Fast | Clean scans | Classic OCR |
| `surya` | Medium | Mixed layouts | Good all-rounder |
| `trocr` | Slow | Handwriting | Microsoft's handwriting model |
| `got_ocr` | Slow | Full documents | VLM - no layout needed |
| `mineru` | Slow | Full documents | VLM - no layout needed |

### Scan Quality Settings
When generating synthetic data, you can choose scan quality:
- **Light**: Minimal noise, slight rotation
- **Medium**: Moderate noise, some blur
- **Heavy**: Significant degradation (stress test)

---

## Tips

1. **Filter by User**: Always use the User dropdown to see only your work
2. **Start Small**: Use 5-10 documents per batch while learning
3. **Compare Fairly**: Run multiple OCR engines on the same batch
4. **Watch Memory**: VLM engines can be slow - be patient
5. **Verify Results**: Use the Verify page to correct OCR mistakes

---

## Troubleshooting

### Test stuck at 0%
- The test may have failed - check for error messages
- Try canceling and running again

### VLM tests very slow
- `got_ocr` and `mineru` are large models running on CPU
- Expected: ~2-3 minutes per document
- For faster results, use `easyocr` or `paddleocr`

### "No batches available"
- Generate synthetic data first
- Check User filter - might be filtering out batches

### Can't see my test results
- Check User filter on Run Tests page
- Test might still be running - check progress

---

## Questions?

Contact Leo for:
- Account creation
- Technical issues
- Feature requests
