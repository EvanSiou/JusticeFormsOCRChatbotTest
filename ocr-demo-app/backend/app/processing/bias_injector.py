"""Automation bias error injection.

Randomly introduces 2 subtle errors into classified fields to prevent
blind acceptance of OCR results. Users must find and correct these errors.
"""
import random
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Visually similar character substitutions
SIMILAR_LETTERS = {
    'a': 'o', 'b': 'd', 'c': 'e', 'd': 'b', 'e': 'c',
    'i': 'l', 'l': 'i', 'm': 'n', 'n': 'm', 'o': 'a',
    'p': 'q', 'q': 'p', 'r': 'n', 's': 'z', 'u': 'v',
    'v': 'u', 'z': 's',
}

SIMILAR_DIGITS = {
    '0': '8', '1': '7', '3': '8', '5': '6', '6': '5',
    '7': '1', '8': '3', '9': '4', '4': '9',
}


def _swap_character(value: str) -> str:
    """Swap a single character with a visually similar one."""
    if len(value) < 2:
        return value

    # Try up to 10 random positions to find a swappable character
    positions = list(range(len(value)))
    random.shuffle(positions)

    for pos in positions:
        char = value[pos]
        replacement = None

        if char.lower() in SIMILAR_LETTERS:
            replacement = SIMILAR_LETTERS[char.lower()]
            if char.isupper():
                replacement = replacement.upper()
        elif char in SIMILAR_DIGITS:
            replacement = SIMILAR_DIGITS[char]

        if replacement and replacement != char:
            return value[:pos] + replacement + value[pos + 1:]

    # Fallback: shift first alphanumeric character by 1
    for pos in range(len(value)):
        if value[pos].isalnum():
            c = value[pos]
            if c.isdigit():
                new_c = str((int(c) + 1) % 10)
            else:
                new_c = chr(ord(c) + 1) if c != 'z' and c != 'Z' else ('a' if c.islower() else 'A')
            return value[:pos] + new_c + value[pos + 1:]

    return value


def inject_bias_errors(
    classified_fields: list[dict],
    num_errors: int = 2,
) -> Tuple[list[dict], list[dict]]:
    """Inject subtle errors into random fields.

    Args:
        classified_fields: List of classified field dicts (must have 'value' key)
        num_errors: Number of errors to inject (default 2)

    Returns:
        (modified_fields, injection_log) where injection_log records what was changed
    """
    # Find eligible fields: non-empty string values with at least 2 chars
    eligible = [
        (i, f) for i, f in enumerate(classified_fields)
        if f.get("value") and isinstance(f["value"], str) and len(f["value"]) >= 2
    ]

    if len(eligible) < num_errors:
        logger.warning(f"Only {len(eligible)} eligible fields for bias injection (need {num_errors})")
        num_errors = len(eligible)

    if num_errors == 0:
        return classified_fields, []

    targets = random.sample(eligible, num_errors)
    injection_log = []
    modified = [dict(f) for f in classified_fields]  # shallow copy each dict

    for idx, field in targets:
        original = field["value"]
        changed = _swap_character(original)

        # Ensure we actually changed something
        if changed == original:
            changed = original[:-1] + _swap_character(original[-1:])

        modified[idx] = {**modified[idx], "value": changed}
        change_type = "digit_swap" if any(c.isdigit() for c in original) else "letter_swap"

        injection_log.append({
            "field_index": idx,
            "field_type": field.get("field_type", ""),
            "original_value": original,
            "injected_value": changed,
            "change_type": change_type,
        })
        logger.info(
            f"Bias injection: field {idx} ({field.get('field_type', '?')}) "
            f"'{original}' -> '{changed}'"
        )

    return modified, injection_log


def validate_bias_corrections(
    user_corrections: list[dict],
    injection_log: list[dict],
) -> dict:
    """Validate that the user found and corrected all injected errors.

    Args:
        user_corrections: List of {field_index, corrected_value} from user
        injection_log: Original injection log from inject_bias_errors

    Returns:
        Dict with passed (bool), found_count, total_errors, details
    """
    found = 0
    details = []

    for inj in injection_log:
        idx = inj["field_index"]
        original = inj["original_value"]

        # Check if user submitted a correction for this field
        user_fix = next(
            (c for c in user_corrections if c.get("field_index") == idx),
            None,
        )

        if user_fix and user_fix.get("corrected_value", "").strip() == original.strip():
            found += 1
            details.append({**inj, "user_found": True, "user_value": user_fix["corrected_value"]})
        else:
            details.append({
                **inj,
                "user_found": False,
                "user_value": user_fix.get("corrected_value") if user_fix else None,
            })

    return {
        "passed": found == len(injection_log),
        "found_count": found,
        "total_errors": len(injection_log),
        "details": details,
    }
