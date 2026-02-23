"""
Normalize classification model responses into a standard format.

Handles multiple response formats:
1. Standard: {"classified_fields": [{"field_type": ..., "value": ..., "confidence": ...}]}
2. Dictionary: {"fields": {"field_name": {"value": ..., "confidence": ...}}}
3. Judge: {"field_evaluations": [...]} — preserved as-is
4. Top-level dict of field_name -> value (flat format)
"""
import logging

logger = logging.getLogger(__name__)


def _dict_to_classified_fields(fields_dict: dict) -> list:
    """Convert a {field_name: value_or_dict} mapping to classified_fields array."""
    normalized = []
    for field_name, field_data in fields_dict.items():
        if isinstance(field_data, dict):
            value = field_data.get("value")
            confidence = field_data.get("confidence", 0.0)
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except (ValueError, TypeError):
                    confidence = 0.0
            normalized.append({
                "field_type": field_name,
                "value": value,
                "confidence": confidence,
                "context": "",
                "page": field_data.get("page", 1),
                "area": field_data.get("area", ""),
            })
        elif isinstance(field_data, list):
            normalized.append({
                "field_type": field_name,
                "value": field_data if field_data else None,
                "confidence": 0.0,
                "context": "",
                "page": 1,
                "area": "",
            })
        else:
            normalized.append({
                "field_type": field_name,
                "value": field_data,
                "confidence": 0.0,
                "context": "",
                "page": 1,
                "area": "",
            })
    return normalized


# Keys that are part of the response metadata, not extracted fields
_META_KEYS = {
    "form_type", "classified_fields", "field_types_used", "error",
    "raw_response", "extraction_quality", "flags", "ocr_text",
    "field_evaluations", "overall_ocr_score", "overall_classification_score",
    "summary", "judge_model", "confidence", "notes", "document_type",
}


def normalize_classification_response(result: dict) -> dict:
    """Normalize a parsed JSON classification response into standard format.

    Converts various response formats into the standard format with
    ``classified_fields`` as a list of dicts with ``field_type``, ``value``,
    ``confidence``, etc.

    Args:
        result: Parsed JSON dict from the model response.

    Returns:
        The same dict, mutated in-place, with ``classified_fields`` guaranteed
        to be a list and ``form_type`` guaranteed to exist.
    """
    # Judge format: preserve field_evaluations, don't force classified_fields
    if "field_evaluations" in result:
        if "classified_fields" not in result:
            result["classified_fields"] = []
        if "form_type" not in result:
            result["form_type"] = "judge_evaluation"
        logger.info(f"Judge format detected: {len(result['field_evaluations'])} field_evaluations")
        return result

    # Format 1: Already has classified_fields array — keep as-is
    if "classified_fields" in result and isinstance(result["classified_fields"], list) and len(result["classified_fields"]) > 0:
        logger.info(f"Standard classified_fields format: {len(result['classified_fields'])} fields")
        if "form_type" not in result:
            result["form_type"] = "unknown"
        return result

    # Format 2: {"fields": {"field_name": {"value": ..., "confidence": ...}}}
    if "fields" in result and isinstance(result["fields"], dict):
        normalized = _dict_to_classified_fields(result["fields"])
        result["classified_fields"] = normalized
        logger.info(
            f"Normalized {len(normalized)} fields from 'fields' dict format"
        )
        if "form_type" not in result:
            result["form_type"] = "unknown"
        return result

    # Format 3: Top-level flat dict — every non-meta key is a field
    # e.g. {"first_name": "John", "last_name": "Doe", "form_type": "registration"}
    if "classified_fields" not in result or result["classified_fields"] == []:
        field_keys = [k for k in result.keys() if k.lower() not in _META_KEYS]
        if field_keys:
            flat_fields = {k: result[k] for k in field_keys}
            normalized = _dict_to_classified_fields(flat_fields)
            result["classified_fields"] = normalized
            logger.info(
                f"Normalized {len(normalized)} fields from top-level flat dict format "
                f"(keys: {field_keys[:10]})"
            )

    # Ensure standard fields exist
    if "form_type" not in result:
        result["form_type"] = "unknown"
    if "classified_fields" not in result:
        result["classified_fields"] = []

    if len(result["classified_fields"]) == 0:
        logger.warning(f"After normalization: 0 classified_fields. Result keys: {list(result.keys())[:15]}")
    else:
        sample = [cf.get("field_type", "?") for cf in result["classified_fields"][:5]]
        logger.info(f"After normalization: {len(result['classified_fields'])} classified_fields. Sample: {sample}")

    return result
