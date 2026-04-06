#!/usr/bin/env python
"""
Verify that all OCR and layout detection libraries are properly installed.
Run this after setting up your environment to check compatibility.
"""

import sys
import os

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

print("=" * 60)
print("Court Date OCR - Environment Verification")
print("=" * 60)
print(f"\nPython version: {sys.version}")
print(f"Python executable: {sys.executable}")
print()

results = []

# Test EasyOCR
print("Testing EasyOCR...", end=" ")
try:
    import easyocr
    print(f"[OK] (version: {easyocr.__version__ if hasattr(easyocr, '__version__') else 'installed'})")
    results.append(("EasyOCR", True, None))
except ImportError as e:
    print(f"[FAILED]: {e}")
    results.append(("EasyOCR", False, str(e)))

# Test Surya OCR
print("Testing Surya OCR...", end=" ")
try:
    # Surya API changed in newer versions - try new API first
    from surya.recognition import RecognitionPredictor
    from surya.detection import DetectionPredictor
    print("[OK] (new API)")
    results.append(("Surya OCR", True, None))
except ImportError:
    try:
        # Fall back to old API
        from surya.ocr import run_ocr
        from surya.detection import batch_text_detection
        print("[OK] (legacy API)")
        results.append(("Surya OCR", True, None))
    except ImportError as e:
        print(f"[FAILED]: {e}")
        results.append(("Surya OCR", False, str(e)))

# Test PaddleOCR (with Python 3.13 workaround)
print("Testing PaddleOCR...", end=" ")
try:
    # Apply workaround for Python 3.13
    os.environ.setdefault('HUB_DATASET_ENDPOINT', 'https://modelscope.cn/api/v1/datasets')
    os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    import paddle
    from paddleocr import PaddleOCR
    print(f"[OK] (PaddlePaddle: {paddle.__version__})")
    results.append(("PaddleOCR", True, None))
except ImportError as e:
    print(f"[FAILED]: {e}")
    results.append(("PaddleOCR", False, str(e)))
except Exception as e:
    print(f"[FAILED]: {e}")
    results.append(("PaddleOCR", False, str(e)))

# Test Tesseract
print("Testing Tesseract...", end=" ")
try:
    import pytesseract
    # Try to get version (this checks if binary is installed)
    version = pytesseract.get_tesseract_version()
    print(f"[OK] (version: {version})")
    results.append(("Tesseract", True, None))
except ImportError as e:
    print(f"[FAILED] (Python package): {e}")
    results.append(("Tesseract", False, str(e)))
except Exception as e:
    print(f"[WARN] Package installed but binary not found: {e}")
    print("   Install Tesseract binary from: https://github.com/UB-Mannheim/tesseract/wiki")
    results.append(("Tesseract", False, "Binary not installed"))

# Test DocLayout-YOLO
print("Testing DocLayout-YOLO...", end=" ")
try:
    from doclayout_yolo import YOLOv10
    print("[OK]")
    results.append(("DocLayout-YOLO", True, None))
except ImportError as e:
    print(f"[FAILED]: {e}")
    results.append(("DocLayout-YOLO", False, str(e)))

# Test DocTR
print("Testing DocTR...", end=" ")
try:
    from doctr.models import detection_predictor
    print("[OK]")
    results.append(("DocTR", True, None))
except ImportError as e:
    print(f"[FAILED]: {e}")
    results.append(("DocTR", False, str(e)))

# Test PyTorch
print("Testing PyTorch...", end=" ")
try:
    import torch
    cuda_available = torch.cuda.is_available()
    cuda_info = f", CUDA: {'available' if cuda_available else 'not available'}"
    print(f"[OK] (version: {torch.__version__}{cuda_info})")
    results.append(("PyTorch", True, None))
except ImportError as e:
    print(f"[FAILED]: {e}")
    results.append(("PyTorch", False, str(e)))

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)

print(f"\nPassed: {passed}/{total}")
print()

if passed < total:
    print("Failed libraries:")
    for name, ok, error in results:
        if not ok:
            print(f"  - {name}: {error}")
    print("\nTo install missing dependencies:")
    print("  pip install -r requirements.txt")
else:
    print("All libraries are working!")

# Check Python version recommendation
if sys.version_info >= (3, 13):
    print("\nNote: You're using Python 3.13+")
    print("   Some libraries may require workarounds.")
    print("   For best compatibility, consider Python 3.11.")
