# OCR Alternative Scripts

Standalone scripts for testing alternative OCR providers against court forms, including skewed and degraded documents.

## Scripts

| File | Description |
|------|-------------|
| `run_skewed_forms.py` | Batch process skewed forms through OCR providers |
| `compare_report.py` | Generate comparison reports across OCR engines |
| `shared_utils.py` | Shared utility functions |

## Provider Tests

| Folder | Description |
|--------|-------------|
| `landingai_test/` | LandingAI OCR provider testing |
| `textract_test/` | AWS Textract OCR provider testing |

## Results

- `skewed_results/` - OCR results from skewed form processing
- `skewed_progress*.json` - Progress tracking for batch runs
