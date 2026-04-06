# Justice Forms OCR

OCR and document intelligence research for statewide justice court forms. This project explores layout detection, text extraction, and field classification pipelines for digitizing handwritten and printed court documents.

## Repository Structure

```
.
├── ocr-testing-app/        # Web application for testing OCR pipelines (FastAPI + React)
├── ocr-testing-notebooks/  # Jupyter notebooks for OCR experimentation and evaluation
├── ocr-testing-forms/      # Sample court form datasets used for testing
├── ocr-scripts/            # Standalone Python scripts and environment setup
├── documents/              # Project documentation, reports, and reference materials
└── venv/                   # Python virtual environment (not committed)
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Google Cloud Project (for Firestore, Cloud Storage, Vertex AI)

### Environment Setup

```bash
cd ocr-testing-app
python -m venv venv
source venv/bin/activate   # Linux/macOS
.\venv\Scripts\Activate    # Windows PowerShell
pip install -r ocr-scripts/requirements.txt
```

See [documents/setup_environment.md](documents/setup_environment.md) for detailed setup instructions.

## Components

### OCR Testing App

Full-stack web application for running OCR tests at scale. Supports multiple OCR engines (PaddleOCR, EasyOCR, Surya, Tesseract, TrOCR, GOT-OCR, MinerU) and layout detection (DocLayout-YOLO). See [ocr-testing-app/README.md](ocr-testing-app/README.md).

### Notebooks

Step-by-step Jupyter notebooks covering the OCR pipeline: document viewing, form filling, scan simulation, layout detection, OCR extraction, visualization, and handwriting generation. See [ocr-testing-notebooks/README.md](ocr-testing-notebooks/README.md).

### Testing Forms

Curated datasets of court forms with handwritten entries from multiple contributors, plus algorithmically skewed variants for robustness testing. See [ocr-testing-forms/README.md](ocr-testing-forms/README.md).

## License

See [documents/LICENSE](documents/LICENSE).
