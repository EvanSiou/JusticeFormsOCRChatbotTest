# OCR Testing Notebooks

Jupyter notebooks covering each stage of the OCR pipeline for court form processing.

## Notebooks

| # | Notebook | Description |
|---|----------|-------------|
| 01 | `01_document_viewer.ipynb` | View and inspect source court form documents |
| 02 | `02_form_filler.ipynb` | Generate synthetic filled forms with handwriting-like data |
| 03 | `03_scan_simulator.ipynb` | Simulate scan artifacts (skew, noise, blur) on clean forms |
| 04 | `04_layout_detection_*.ipynb` | Layout detection using DocLayout-YOLO, docTR, and Surya |
| 05 | `05_ocr_extraction_*.ipynb` | Text extraction using EasyOCR, PaddleOCR, and Surya |
| 06 | `06_visualization.ipynb` | Visualize and compare OCR results across engines |
| 07 | `07_diffusion_pen.ipynb` | Handwriting generation with DiffusionPen |

## Setup

These notebooks require the project virtual environment. From the repository root:

```bash
source venv/bin/activate
pip install -r ocr-scripts/requirements.txt
jupyter lab
```

## Supporting Files

- `DiffusionPen/` - DiffusionPen model for handwriting synthesis
- `diffusionpen_output/` - Generated handwriting samples
- `field_configs/` - Field configuration files for form processing
