# OCR Testing Forms

Sample court form datasets used for OCR pipeline testing and evaluation.

## Datasets

| Folder | Description |
|--------|-------------|
| `Hasan/` | Handwritten court forms contributed by Hasan |
| `Quareen/` | Handwritten court forms contributed by Quareen |
| `Sadam/` | Handwritten court forms contributed by Sadam |
| `skewed_forms/` | Algorithmically skewed variants for robustness testing |

## Skewed Forms

The `skewed_forms/` directory contains programmatically distorted versions of clean forms to test OCR resilience:

- `originals/` - Original clean scans
- `heavy_skew/` - Heavily rotated/distorted variants
- `180_clean/` - 180-degree rotated clean forms

## Usage

These forms are used as input data for:
- The OCR testing notebooks (`ocr-testing-notebooks/`)
- The OCR testing web application (`ocr-testing-app/`)
- Batch evaluation scripts (`ocr-scripts/`)
