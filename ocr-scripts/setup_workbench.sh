#!/bin/bash
# Setup script for Vertex AI Workbench
# Run this after cloning the repository to the Workbench instance

set -e

echo "==================================="
echo "Setting up OCR Testing Environment"
echo "==================================="

# Check Python version
python3 --version

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install Tesseract OCR binary (for pytesseract)
echo "Installing Tesseract OCR..."
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng

# Install poppler for pdf2image
echo "Installing Poppler..."
sudo apt-get install -y poppler-utils

# Install Python dependencies
echo "Installing Python packages..."
pip install -r requirements-cloud.txt

# Verify installations
echo ""
echo "==================================="
echo "Verifying installations..."
echo "==================================="

python3 << 'EOF'
import sys
print(f"Python: {sys.version}")

libraries = [
    ("easyocr", "easyocr"),
    ("surya", "surya.recognition"),
    ("paddleocr", "paddleocr"),
    ("pytesseract", "pytesseract"),
    ("doclayout_yolo", "doclayout_yolo"),
    ("doctr", "doctr.models"),
    ("torch", "torch"),
    ("google-cloud-storage", "google.cloud.storage"),
    ("google-cloud-vision", "google.cloud.vision"),
]

print("\nLibrary Status:")
print("-" * 40)
for name, module in libraries:
    try:
        __import__(module)
        print(f"  [OK] {name}")
    except ImportError as e:
        print(f"  [FAIL] {name}: {e}")

print("\nSetup complete!")
EOF

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Upload your documents to ./filled_documents/"
echo "2. Run the layout detection notebooks (04_*)"
echo "3. Run the OCR extraction notebooks (05_*)"
echo "4. View results in ./ocr_results/"
