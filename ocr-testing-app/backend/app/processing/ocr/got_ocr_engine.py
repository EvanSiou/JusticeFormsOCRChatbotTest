"""
GOT-OCR2.0 engine implementation.

Uses stepfun-ai/GOT-OCR-2.0-hf - a unified end-to-end OCR model (580M params).
Handles plain text, formatted text, tables, formulas, etc.
Uses the HuggingFace transformers integration.

This engine processes the FULL PAGE in a single pass for efficiency,
ignoring the layout regions since GOT-OCR is designed for end-to-end OCR.
"""
from typing import List
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class GotOCREngine(OCREngineBase):
    """OCR engine using GOT-OCR2.0 (General OCR Theory)."""

    _processor = None
    _model = None

    @property
    def name(self) -> str:
        return "got_ocr"

    _device = None

    def _load_model(self):
        """Lazy load GOT-OCR2.0 model and processor."""
        if GotOCREngine._processor is None:
            import torch
            from transformers import AutoProcessor, AutoModelForImageTextToText

            model_name = "stepfun-ai/GOT-OCR-2.0-hf"

            # Use GPU if available
            GotOCREngine._device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if GotOCREngine._device == "cuda" else torch.float32

            GotOCREngine._processor = AutoProcessor.from_pretrained(
                model_name,
                use_fast=True,
            )
            GotOCREngine._model = AutoModelForImageTextToText.from_pretrained(
                model_name,
                device_map=GotOCREngine._device,
                torch_dtype=dtype,
            )
            GotOCREngine._model.eval()

        return GotOCREngine._processor, GotOCREngine._model

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text from the FULL PAGE in a single pass.

        GOT-OCR is an end-to-end VLM designed to process full documents.
        Processing per-region is inefficient and slow. Instead, we process
        the entire page once and return all text as a single region result.
        """
        # Process the full page image once
        full_page_result = self._process_full_page(image)

        # Return as a single result (region_id=0 for full page)
        return [full_page_result]

    def _process_full_page(self, image: Image.Image) -> OCRResult:
        """Process the full page image with GOT-OCR2.0 in a single pass."""
        import torch

        processor, model = self._load_model()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Process full image through GOT-OCR2.0
        inputs = processor(
            image,
            return_tensors="pt",
        ).to(GotOCREngine._device)

        with torch.no_grad():
            generate_ids = model.generate(
                **inputs,
                do_sample=False,
                tokenizer=processor.tokenizer,
                stop_strings="<|im_end|>",
                max_new_tokens=4096,
            )

        # Decode the generated text
        full_text = processor.decode(
            generate_ids[0, inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        # Split into lines
        lines = []
        if full_text:
            text_lines = full_text.split('\n')
            for i, line_text in enumerate(text_lines):
                line_text = line_text.strip()
                if not line_text:
                    continue

                lines.append(TextLine(
                    text=line_text,
                    confidence=0.95,  # GOT-OCR doesn't expose confidence scores
                    bbox_in_region={
                        "x1": 0,
                        "y1": 0,
                        "x2": image.width,
                        "y2": image.height,
                    }
                ))

        return OCRResult(
            region_id=0,  # Full page = region 0
            full_text=full_text,
            lines=lines,
        )

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """
        Process a cropped image with GOT-OCR2.0.

        Note: This method is kept for compatibility but extract_text()
        now uses full-page processing for efficiency.
        """
        import torch

        processor, model = self._load_model()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Process image through GOT-OCR2.0
        inputs = processor(
            image,
            return_tensors="pt",
        ).to(GotOCREngine._device)

        with torch.no_grad():
            generate_ids = model.generate(
                **inputs,
                do_sample=False,
                tokenizer=processor.tokenizer,
                stop_strings="<|im_end|>",
                max_new_tokens=4096,
            )

        # Decode the generated text
        full_text = processor.decode(
            generate_ids[0, inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        # GOT-OCR2.0 returns full text; split into lines
        lines = []
        if full_text:
            text_lines = full_text.split('\n')
            for i, line_text in enumerate(text_lines):
                line_text = line_text.strip()
                if not line_text:
                    continue

                lines.append(TextLine(
                    text=line_text,
                    confidence=0.95,  # GOT-OCR doesn't expose confidence scores
                    bbox_in_region={
                        "x1": 0,
                        "y1": 0,
                        "x2": image.width,
                        "y2": image.height,
                    }
                ))

        return OCRResult(
            region_id=region_id,
            full_text=full_text,
            lines=lines,
        )
