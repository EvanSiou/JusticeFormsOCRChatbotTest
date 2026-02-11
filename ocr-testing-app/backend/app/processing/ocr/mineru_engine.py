"""
MinerU OCR engine implementation.

Uses opendatalab/MinerU2.5-2509-1.2B - a 1.2B parameter multimodal document
parsing model based on Qwen2VL. Handles text, tables, formulas, and more.

This engine processes the FULL PAGE in a single pass for efficiency,
using MinerU's built-in layout detection + OCR pipeline.
"""
from typing import List
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class MinerUEngine(OCREngineBase):
    """OCR engine using MinerU (opendatalab/MinerU2.5-2509-1.2B)."""

    _client = None
    _device = None

    @property
    def name(self) -> str:
        return "mineru"

    def _load_model(self):
        """Lazy load MinerU model and client."""
        if MinerUEngine._client is None:
            import torch
            from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
            from mineru_vl_utils import MinerUClient

            model_name = "opendatalab/MinerU2.5-2509-1.2B"

            # Use GPU if available
            MinerUEngine._device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if MinerUEngine._device == "cuda" else torch.float32

            model = Qwen2VLForConditionalGeneration.from_pretrained(
                model_name,
                torch_dtype=dtype,
                device_map=MinerUEngine._device,
            )

            processor = AutoProcessor.from_pretrained(
                model_name,
                use_fast=True,
            )

            MinerUEngine._client = MinerUClient(
                backend="transformers",
                model=model,
                processor=processor,
            )

        return MinerUEngine._client

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text from the FULL PAGE in a single pass.

        MinerU is an end-to-end VLM with built-in layout detection.
        Processing per-region is inefficient and slow. Instead, we process
        the entire page once using MinerU's two_step_extract which does
        its own layout detection + content recognition.
        """
        # Process the full page image once
        full_page_result = self._process_full_page(image)

        # Return as a single result (region_id=0 for full page)
        return [full_page_result]

    def _process_full_page(self, image: Image.Image) -> OCRResult:
        """Process the full page image with MinerU in a single pass."""
        client = self._load_model()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        img_w, img_h = image.size

        # Use MinerU's two-step extraction (layout detect + content recognize)
        try:
            blocks = client.two_step_extract(image)
        except Exception as e:
            # Fallback: return empty result if MinerU fails
            return OCRResult(
                region_id=0,
                full_text="",
                lines=[],
            )

        lines = []
        full_text_parts = []

        for block in blocks:
            # Extract text content (skip non-text blocks like images)
            content = getattr(block, 'content', None) or ''
            block_type = getattr(block, 'type', 'text')
            bbox = getattr(block, 'bbox', None)

            if not content:
                continue

            # Convert normalized bbox [0,1] to pixel coordinates
            if bbox and len(bbox) == 4:
                x1 = int(bbox[0] * img_w)
                y1 = int(bbox[1] * img_h)
                x2 = int(bbox[2] * img_w)
                y2 = int(bbox[3] * img_h)
            else:
                x1, y1, x2, y2 = 0, 0, img_w, img_h

            # For text blocks, split multi-line content
            text_lines = content.strip().split('\n')
            for line_text in text_lines:
                line_text = line_text.strip()
                if not line_text:
                    continue

                lines.append(TextLine(
                    text=line_text,
                    confidence=0.9,  # MinerU doesn't expose per-block confidence
                    bbox_in_region={
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                    }
                ))
                full_text_parts.append(line_text)

        full_text = " ".join(full_text_parts)

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
        Process a cropped image with MinerU.

        Note: This method is kept for compatibility but extract_text()
        now uses full-page processing for efficiency.
        """
        client = self._load_model()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Use MinerU's two-step extraction (layout detect + content recognize)
        try:
            blocks = client.two_step_extract(image)
        except Exception as e:
            # Fallback: return empty result if MinerU fails on this region
            return OCRResult(
                region_id=region_id,
                full_text="",
                lines=[],
            )

        lines = []
        full_text_parts = []
        img_w, img_h = image.size

        for block in blocks:
            # Extract text content (skip non-text blocks like images)
            content = getattr(block, 'content', None) or ''
            block_type = getattr(block, 'type', 'text')
            bbox = getattr(block, 'bbox', None)

            if not content:
                continue

            # Convert normalized bbox [0,1] to pixel coordinates
            if bbox and len(bbox) == 4:
                x1 = int(bbox[0] * img_w)
                y1 = int(bbox[1] * img_h)
                x2 = int(bbox[2] * img_w)
                y2 = int(bbox[3] * img_h)
            else:
                x1, y1, x2, y2 = 0, 0, img_w, img_h

            # For text blocks, split multi-line content
            text_lines = content.strip().split('\n')
            for line_text in text_lines:
                line_text = line_text.strip()
                if not line_text:
                    continue

                lines.append(TextLine(
                    text=line_text,
                    confidence=0.9,  # MinerU doesn't expose per-block confidence
                    bbox_in_region={
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                    }
                ))
                full_text_parts.append(line_text)

        full_text = " ".join(full_text_parts)

        return OCRResult(
            region_id=region_id,
            full_text=full_text,
            lines=lines,
        )
