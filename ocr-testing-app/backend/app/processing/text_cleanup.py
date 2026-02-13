"""
Template text cleanup module.

Removes known template words (form labels, underscores, static text)
from OCR output, leaving only human-added content.
"""
import re
import copy
from difflib import SequenceMatcher
from typing import List

from app.processing.ocr.base import OCRResult, TextLine


class TemplateTextCleaner:
    """Removes known template text from OCR output."""

    def __init__(self, template_words: List[str]):
        """
        Args:
            template_words: List of known template words/phrases to remove.
                           Each entry is a line or phrase from the blank form.
        """
        self.template_lines = [w.strip() for w in template_words if w.strip()]
        self.template_lines_lower = [w.lower() for w in self.template_lines]

    def clean(self, ocr_text: str) -> str:
        """
        Remove template text from OCR output.

        Strategy:
        1. For each OCR line, fuzzy-match against template lines
        2. Remove lines that match (ratio >= 0.85)
        3. Remove decoration patterns (underscores, dashes, dots)
        4. Return remaining text
        """
        if not self.template_lines:
            return ocr_text

        result_lines = []
        for line in ocr_text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            # Skip decoration-only lines
            if self._is_decoration(stripped):
                continue

            # Check if this line matches any template line
            if self._matches_template(stripped):
                continue

            # Clean individual template words from within the line
            cleaned = self._remove_template_fragments(stripped)
            cleaned = cleaned.strip()
            if cleaned and not self._is_decoration(cleaned):
                result_lines.append(cleaned)

        return '\n'.join(result_lines)

    def _matches_template(self, line: str) -> bool:
        """Check if a line fuzzy-matches any template line."""
        line_lower = line.lower()
        for template_line in self.template_lines_lower:
            ratio = SequenceMatcher(None, line_lower, template_line).ratio()
            if ratio >= 0.85:
                return True
        return False

    def _remove_template_fragments(self, line: str) -> str:
        """Remove template word fragments from within a line."""
        result = line
        for template_word in self.template_lines:
            if len(template_word) < 3:
                continue
            # Only remove if the template word appears as a recognizable substring
            idx = result.lower().find(template_word.lower())
            if idx != -1:
                result = result[:idx] + result[idx + len(template_word):]
        return result

    @staticmethod
    def _is_decoration(text: str) -> bool:
        """Check if text is purely decorative (underscores, dashes, dots)."""
        cleaned = re.sub(r'[_\-.\s:]+', '', text)
        return len(cleaned) == 0

    @staticmethod
    def clean_ocr_results(
        ocr_results_list: List[OCRResult],
        template_words: List[str],
    ) -> List[OCRResult]:
        """
        Create cleaned copies of OCRResult objects for field matching.

        Args:
            ocr_results_list: Original OCR results
            template_words: Known template words to remove

        Returns:
            New list of OCRResult objects with cleaned text
        """
        cleaner = TemplateTextCleaner(template_words)
        cleaned_results = []

        for result in ocr_results_list:
            cleaned_lines = []
            cleaned_full_parts = []

            for line in result.lines:
                cleaned_text = cleaner.clean(line.text)
                if cleaned_text.strip():
                    cleaned_lines.append(TextLine(
                        text=cleaned_text.strip(),
                        confidence=line.confidence,
                        bbox_in_region=line.bbox_in_region,
                    ))
                    cleaned_full_parts.append(cleaned_text.strip())

            cleaned_results.append(OCRResult(
                region_id=result.region_id,
                full_text=' '.join(cleaned_full_parts),
                lines=cleaned_lines,
            ))

        return cleaned_results
