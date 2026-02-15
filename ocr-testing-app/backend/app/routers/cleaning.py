"""
Text cleaning routes.
Allows users to preview and save cleaned OCR text.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from app.auth.dependencies import get_current_user_id
from app.models.cleaning import (
    CleanPreviewRequest,
    CleanSaveRequest,
    CleanedDocumentPreview,
    CleanPreviewResponse,
)
from app.services.firestore import FirestoreService
from app.processing.text_cleanup import TemplateTextCleaner

router = APIRouter()

# Standard decoration patterns and court form template unigrams to remove
STANDARD_PATTERNS = [
    # Decoration patterns
    "____", "________", "____________", "________________",
    "____________________", "________________________",
    "----", "--------", "------------",
    "....", "........", "............",
    "::::", "========",
    "( )", "(  )", "[  ]", "[ ]",
    "__.m.",
    "20____",
    # Court form template unigrams (unique words from Personal Bond - Magistration)
    "CAUSE", "NO.",
    "STATE", "OF", "TEXAS",
    "IN", "THE", "JUSTICE", "COURT",
    "PRECINCT",
    "v.",
    "DEFENDANT", "DEFENDANT.",
    "COUNTY,", "COUNTY",
    "PERSONAL", "BOND", "MAGISTRATION",
    "On", "Defendant", "Defendant's",
    "appeared", "before", "me", "as", "a", "magistrate", "on", "the", "charge", "of",
    "which", "is", "is:",
    "This", "this",
    "eligible", "for", "release", "personal", "bond", "bond.",
    "under", "Code", "Criminal", "Procedure", "Art.", "17.03(b),",
    "and", "not", "civilly", "committed", "sexually", "violent", "predator",
    "Health", "Safety", "Chapter", "841.",
    "obligation", "remains", "in", "full", "effect", "until",
    "court", "court,", "court.", "disposes", "discharges",
    "Additional", "conditions", "release,", "if", "any,", "are", "follows,",
    "or", "an", "attached", "Condition", "order:",
    "fee", "authorized", "by", "17.42",
    "Waived.", "Assessed", "amount",
    "ORDERED", "to", "be", "paid", "costs",
    "condition",
    "I,", "I", "case,", "acknowledge", "that", "have", "been", "charged", "with",
    "offense", "indicated", "above.",
    "enter", "into", "freely", "voluntarily.",
    "swear", "will", "appear", "appear.", "at",
    "otherwise", "directed",
    "pay", "sum",
    "plus", "all", "necessary", "reasonable", "expenses", "incurred", "any", "arrest",
    "failure",
    "payable",
    "Signature", "Date",
    "Interpreter's", "(if", "any)",
    "Printed", "Name",
    # Standalone punctuation and short patterns
    "§",
    "_", ".", "(", ")", "$_",
    # Multi-word phrases
    "if any", "(if any)", "(ifany)",
    "Procedure Art", "by Code of Criminal",
    # Additional template words
    "Art,", "Interpreters",
]


def _build_word_list(
    use_standard_patterns: bool,
    custom_words: List[str] | None,
) -> List[str]:
    """Combine standard patterns and custom words into a single list."""
    words: List[str] = []
    if use_standard_patterns:
        words.extend(STANDARD_PATTERNS)
    if custom_words:
        words.extend([w.strip() for w in custom_words if w.strip()])
    return words


@router.post("/preview", response_model=CleanPreviewResponse)
async def preview_cleaning(
    request: CleanPreviewRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Preview text cleaning on all documents in a test run."""
    firestore = FirestoreService()

    test_run = await firestore.get_test_run_by_id(request.test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found",
        )

    words = _build_word_list(request.use_standard_patterns, request.custom_words)
    if not words:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No cleaning words specified. Enable standard patterns or provide custom words.",
        )

    cleaner = TemplateTextCleaner(words)
    results = await firestore.get_results_by_test_run(request.test_run_id)

    documents: List[CleanedDocumentPreview] = []
    for result in results:
        full_text = result.ocr_results.get("full_text", "")
        if not full_text:
            continue

        cleaned = cleaner.clean(full_text)
        documents.append(CleanedDocumentPreview(
            document_id=result.document_id,
            result_id=result.id,
            original_text=full_text,
            cleaned_text=cleaned,
        ))

    return CleanPreviewResponse(
        documents=documents,
        total=len(documents),
        words_used=words,
    )


@router.put("/{test_run_id}/save")
async def save_cleaned_text(
    test_run_id: str,
    request: CleanSaveRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Clean and persist cleaned text for all documents in a test run."""
    firestore = FirestoreService()

    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found",
        )

    words = _build_word_list(request.use_standard_patterns, request.custom_words)
    if not words:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No cleaning words specified.",
        )

    cleaner = TemplateTextCleaner(words)
    results = await firestore.get_results_by_test_run(test_run_id)

    saved_count = 0
    for result in results:
        full_text = result.ocr_results.get("full_text", "")
        if not full_text:
            continue

        cleaned = cleaner.clean(full_text)
        success = await firestore.update_result_cleaned_text(result.id, cleaned)
        if success:
            saved_count += 1

    return {
        "message": "Cleaned text saved",
        "test_run_id": test_run_id,
        "documents_cleaned": saved_count,
    }


@router.get("/{test_run_id}/status")
async def get_cleaning_status(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get cleaning status for a test run."""
    firestore = FirestoreService()

    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found",
        )

    results = await firestore.get_results_by_test_run(test_run_id)

    total = len(results)
    cleaned = sum(
        1 for r in results
        if r.ocr_results.get("cleaned_text")
    )

    return {
        "test_run_id": test_run_id,
        "total_documents": total,
        "documents_with_cleaned_text": cleaned,
    }
