"""PIL-based page auto-correction using quality detection results."""
import logging
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


def correct_page(image: Image.Image, quality_data: dict) -> Image.Image:
    """Apply corrections based on quality detection results.

    Args:
        image: Original page image
        quality_data: Dict from quality_detector with skew_angle, rotation_needed, etc.

    Returns:
        Corrected PIL Image
    """
    img = image.copy()
    corrections_applied = []

    # 1. Major rotation correction (90/180/270)
    rotation_needed = quality_data.get("rotation_needed", 0)
    if rotation_needed and rotation_needed in (90, 180, 270):
        img = img.rotate(-rotation_needed, expand=True, fillcolor=(255, 255, 255))
        corrections_applied.append(f"rotated {rotation_needed} degrees")

    # 2. Deskew (fine angle correction)
    skew_angle = quality_data.get("skew_angle", 0.0)
    if abs(skew_angle) > 0.5:
        img = img.rotate(-skew_angle, expand=True, fillcolor=(255, 255, 255))
        corrections_applied.append(f"deskewed {skew_angle:.1f} degrees")

    # 3. Contrast enhancement
    contrast = quality_data.get("contrast_quality", 1.0)
    if contrast < 0.7:
        boost = 1.0 + (0.7 - contrast)
        img = ImageEnhance.Contrast(img).enhance(boost)
        corrections_applied.append(f"contrast boost {boost:.2f}x")

    # 4. Noise reduction
    noise = quality_data.get("noise_level", 0.0)
    if noise > 0.4:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        corrections_applied.append("noise reduction")

    # 5. Sharpening (restore text edges after any blur)
    if noise > 0.4 or contrast < 0.7:
        img = img.filter(ImageFilter.SHARPEN)
        corrections_applied.append("sharpened")

    # 6. Brightness adjustment for dark scans
    degradation = quality_data.get("degradation_score", 0.0)
    if degradation > 0.3:
        brightness_boost = 1.0 + (degradation * 0.2)
        img = ImageEnhance.Brightness(img).enhance(brightness_boost)
        corrections_applied.append(f"brightness {brightness_boost:.2f}x")

    if corrections_applied:
        logger.info(f"Page corrections applied: {', '.join(corrections_applied)}")
    else:
        logger.info("No corrections needed")

    return img
