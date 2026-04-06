"""
AWS Textract test runner.

Runs AnalyzeDocument (Forms) on prisoner registration forms,
compares extracted fields to ground truth using Claude as judge.

Usage:
    python textract_runner.py                  # Run all 60 originals
    python textract_runner.py --doc 1          # Run single doc (for testing)
    python textract_runner.py --skew           # Include skew variants
    python textract_runner.py --report         # Print report from saved results
    python textract_runner.py --loop           # Run continuously until done
"""
import os
import sys
import json
import time
import logging
import argparse

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shared_utils as utils

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "textract.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("textract_runner")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(SCRIPT_DIR, "..", "..", "Documents")  # Documents folder
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "textract_progress.json")
RESULTS_FILE = os.path.join(RESULTS_DIR, "textract_results.json")


# ── Textract Response Parser ──

def parse_textract_kv_pairs(response):
    """Parse Textract AnalyzeDocument response into {key: value} dict.

    Traverses KEY_VALUE_SET blocks and their relationships to reconstruct
    key-value pairs from the form.
    """
    blocks = response.get("Blocks", [])
    block_map = {b["Id"]: b for b in blocks}

    def get_text(block):
        """Get text content from a block by following CHILD relationships."""
        text_parts = []
        if "Relationships" in block:
            for rel in block["Relationships"]:
                if rel["Type"] == "CHILD":
                    for child_id in rel["Ids"]:
                        child = block_map.get(child_id, {})
                        if child.get("BlockType") in ("WORD", "SELECTION_ELEMENT"):
                            if child["BlockType"] == "WORD":
                                text_parts.append(child.get("Text", ""))
                            elif child["BlockType"] == "SELECTION_ELEMENT":
                                text_parts.append("SELECTED" if child.get("SelectionStatus") == "SELECTED" else "NOT_SELECTED")
        return " ".join(text_parts).strip()

    def get_value_block(key_block):
        """Find the VALUE block associated with a KEY block."""
        if "Relationships" in key_block:
            for rel in key_block["Relationships"]:
                if rel["Type"] == "VALUE":
                    for val_id in rel["Ids"]:
                        return block_map.get(val_id)
        return None

    # Return list of (key, value) tuples to preserve order and duplicates
    kv_pairs = []
    for block in blocks:
        if block.get("BlockType") == "KEY_VALUE_SET" and "KEY" in block.get("EntityTypes", []):
            key_text = get_text(block)
            value_block = get_value_block(block)
            value_text = get_text(value_block) if value_block else ""
            if key_text:
                kv_pairs.append((key_text, value_text))

    return kv_pairs


def map_textract_to_fields(page1_kvs, page2_kvs):
    """Map Textract key-value pairs to ground truth field names.

    Args:
        page1_kvs: list of (key, value) tuples from page 1
        page2_kvs: list of (key, value) tuples from page 2

    Returns: (mapped_fields dict, unmapped_keys list of (key, value))
    """
    # Page 1 unique-key mappings
    PAGE1_MAP = {
        ". Officer Last Name": "officer_last_name",
        ". Officer First Name": "officer_first_name",
        ". Badge Number": "badge_number",
        ". Employee ID Number": "employee_id_number",
        "* Contact Phone Number": "contact_phone_number",
        ". Agency": "agency",
        ". Last Name": "last_name",
        "Social Security Number": "ssn",
        "* Date of Birth": "date_of_birth",
        "Age": "age",
        "* Race": "race",
        "Citizenship": "citizenship",
        "Country of Birth": "country_of_birth",
        "City of Birth": "city_of_birth",
        ". Height": "height",
        ". Weight": "weight",
        "* Eyes": "eyes",
        "* Skin": "skin",
        "* Hair Type": "hair_type",
        ". Hair Length": "hair_length",
        ". Hair Color": "hair_color",
        "Marital Status": "marital_status",
        "* Religious Preference": "religious_preference",
        "Agency Wanting Person": "agency_wanting_person",
        "Agency Contact Person": "agency_contact_person",
        "HCSO SPN": "hcso_spn",
        "State-Issued ID Number": "state_issued_id_number",
        "Issuing State": "issuing_state",
        "Driver's License Number": "drivers_license_number",
        "DL State": "dl_state",
        "DL Type": "dl_type",
        "SID Number": "sid_number",
        "FBI Number": "fbi_number",
        "AFIS Number": "afis_number",
        "so Number": "so_number",
        "DA Log Number": "da_log_number",
        "Assistant DA Name": "assistant_da_name",
        ". ADDRESS: Type": "address_type",
        "Address": "address_street",
        "Employer Name": "employer_name",
        "Occupation": "occupation",
        "Employer Street Address": "employer_address",
        "Employer Phone Number": "employer_phone",
        "Relationship": "emergency_relationship",
    }

    PAGE2_MAP = {
        ". ARRESTING OFFICER: Last Name": "arr_officer_last_name",
        ". First Name": "arr_officer_first_name",
        ". Badge #": "arr_officer_badge",
        ". Employee ID #": "arr_officer_employee_id",
        ". Contact #": "arr_officer_contact",
        "TRANSPORTING OFFICER: Last Name": "trans_officer_last_name",
        ". Arrest Location": "arrest_location",
        ". Date": "arrest_date",
        ". Time": "arrest_time",
        ". Prisoner Health Condition": "prisoner_health_condition",
        "Prisoner's Signature": "prisoner_signature",
        "Officer's Signature": "officer_signature",
    }

    # Checkbox fields: key text -> (field_name, value_if_selected)
    CHECKBOX_MAP = {
        "M": ("sex", "M"), "F": ("sex", "F"),
        "Arresting": ("officer_type", "Arresting"),
        "Transporting": ("officer_type", "Transporting"),
        "Both": ("officer_type", "Both"),
        "Hispanic": ("ethnicity", "Hispanic"),
        "Non-Hispanic": ("ethnicity", "Non-Hispanic"),
        "Thin": ("build", "Thin"), "Skinny": ("build", "Skinny"),
        "Obese": ("build", "Obese"),
        "Goatee": ("beard", "Goatee"),
        "None": ("beard", "None"),
    }

    # "Medium" and "Heavy" are ambiguous (could be build or hair).
    # We handle them by tracking which appears as SELECTED.
    BUILD_CHECKBOXES = {"Medium", "Heavy"}

    mapped = {}
    unmapped = []

    # ── Process Page 1 (ordered tuples) ──
    # Track occurrence counts for duplicate keys
    counts = {}
    smt_idx = 0  # Track SMT entries (1, 2, 3)

    # First pass: collect Y/N checkbox positions by tracking sequence
    # Y/N checkboxes map to: veteran, using_drugs, using_alcohol, wanted, mustache, glasses
    # These appear in form order on page 1
    yn_fields = []  # Will collect (key, value) for Y/N pairs

    for key, value in page1_kvs:
        clean_key = key.strip()
        counts[clean_key] = counts.get(clean_key, 0) + 1
        occurrence = counts[clean_key]

        # Checkbox fields (SELECTED/NOT_SELECTED)
        if "SELECTED" in value:
            if clean_key in CHECKBOX_MAP:
                if value == "SELECTED":
                    field_name, field_value = CHECKBOX_MAP[clean_key]
                    mapped[field_name] = field_value
                continue

            if clean_key in BUILD_CHECKBOXES:
                if value == "SELECTED":
                    mapped["build"] = clean_key
                continue

            if clean_key in ("Y", "N"):
                yn_fields.append((clean_key, value))
                continue

            # Skip other checkboxes (Light for hair, etc.)
            if clean_key in ("Light",):
                continue

            continue

        # Skip low-value keys
        if clean_key in ("Rev.", "Required"):
            continue

        # Unique keys
        if clean_key in PAGE1_MAP:
            mapped[PAGE1_MAP[clean_key]] = value
            continue

        # Duplicate keys handled by occurrence count
        if clean_key == "First Name":
            if occurrence == 1:
                mapped["first_name"] = value
            elif occurrence == 2:
                mapped["emergency_first_name"] = value
            continue

        if clean_key == "Last Name":
            if occurrence == 1:
                mapped["emergency_last_name"] = value
            continue

        if clean_key == "Middle Name":
            if occurrence == 1:
                mapped["middle_name"] = value
            elif occurrence == 2:
                mapped["emergency_middle_name"] = value
            continue

        if clean_key == "City":
            if occurrence == 1:
                mapped["address_city"] = value
            elif occurrence == 2:
                mapped["employer_city"] = value
            continue

        if clean_key == "State":
            if occurrence == 1:
                mapped["address_state"] = value
            elif occurrence == 2:
                mapped["employer_state"] = value
            continue

        if clean_key == "ZIP Code":
            if occurrence == 1:
                mapped["address_zip"] = value
            elif occurrence == 2:
                mapped["employer_zip"] = value
            continue

        if clean_key == "Source":
            source_fields = ["address_source", "phone_1_source", "emergency_source", "employer_source"]
            if occurrence <= len(source_fields):
                mapped[source_fields[occurrence - 1]] = value
            continue

        if clean_key == "Phone Number":
            phone_fields = ["phone_1_number", "phone_2_number", "emergency_phone"]
            if occurrence <= len(phone_fields):
                if value:  # skip empty phone numbers
                    mapped[phone_fields[occurrence - 1]] = value
            continue

        if clean_key == "Phone Type":
            mapped["phone_1_type"] = value
            continue

        if clean_key == "TELEPHONE: Type":
            mapped["phone_2_type"] = value
            continue

        if clean_key == "Type":
            if occurrence == 1:
                mapped["employer_phone_type"] = value
            continue

        # SMT fields (Scars/Marks/Tattoos) — appear in groups of 3
        if clean_key == "SCARS MARKS TATTOOS: Type":
            smt_idx += 1
            if value:
                mapped[f"smt_{smt_idx}_type"] = value
            continue
        if clean_key == "Location":
            if value:
                mapped[f"smt_{smt_idx}_location"] = value
            continue
        if clean_key == "Description":
            if value and smt_idx > 0:
                mapped[f"smt_{smt_idx}_description"] = value
            continue

        unmapped.append((f"p1:{clean_key}", value))

    # Map Y/N checkboxes to fields in form order
    # Form order: veteran(Y/N), using_drugs(Y/N), using_alcohol(Y/N), wanted(Y/N), mustache(Y/N), glasses(Y/N)
    yn_field_order = ["veteran", "using_drugs", "using_alcohol", "wanted", "mustache", "glasses"]
    yn_pair_idx = 0
    i = 0
    while i < len(yn_fields) and yn_pair_idx < len(yn_field_order):
        key, value = yn_fields[i]
        if value == "SELECTED":
            mapped[yn_field_order[yn_pair_idx]] = key  # "Y" or "N"
            yn_pair_idx += 1
            # Skip the paired checkbox (the other option)
            if i + 1 < len(yn_fields):
                i += 2
            else:
                i += 1
        else:
            i += 1

    # ── Process Page 2 (ordered tuples) ──
    counts2 = {}
    property_section = None  # track which property section we're in
    p2_arresting_agency_count = 0

    for key, value in page2_kvs:
        clean_key = key.strip()
        counts2[clean_key] = counts2.get(clean_key, 0) + 1
        occurrence = counts2[clean_key]

        # Skip checkboxes on page 2 (charge types, etc.)
        if "SELECTED" in value:
            # Unusual behavior Yes/No
            if clean_key == "Yes" and occurrence == 1:
                if value == "SELECTED":
                    mapped["unusual_behavior"] = "Yes"
            elif clean_key == "No" and "unusual_behavior" not in mapped:
                if value == "SELECTED":
                    mapped["unusual_behavior"] = "No"
            # Phone numbers opportunity
            if clean_key == "Yes" and occurrence == 2:
                if value == "SELECTED":
                    mapped["phone_numbers_opportunity"] = "Yes"
            continue

        if clean_key in ("Rev.",):
            continue

        # Unique page 2 keys
        if clean_key in PAGE2_MAP:
            mapped[PAGE2_MAP[clean_key]] = value
            continue

        # Arresting agency appears twice on page 2
        if clean_key == ". Arresting Agency":
            p2_arresting_agency_count += 1
            if p2_arresting_agency_count == 1:
                mapped["arr_officer_agency"] = value
            elif p2_arresting_agency_count == 2:
                mapped["arresting_agency"] = value
            continue

        # Unit # duplicates: arresting officer then transporting
        if clean_key == "Unit #":
            if occurrence == 1:
                mapped["arr_officer_unit"] = value
            elif occurrence == 2:
                mapped["trans_officer_unit"] = value
            continue

        # Transporting officer fields
        if clean_key == "First Name":
            mapped["trans_officer_first_name"] = value
            continue
        if clean_key == "Badge #":
            mapped["trans_officer_badge"] = value
            continue
        if clean_key == "Employee ID #":
            mapped["trans_officer_employee_id"] = value
            continue
        if clean_key == "Contact #":
            mapped["trans_officer_contact"] = value
            continue
        if clean_key == "Agency":
            mapped["trans_officer_agency"] = value
            continue

        # Property section — Item/Description/Color/Quantity groups
        if clean_key == "Valuable Property Bags":
            property_section = "valuable"
            continue
        if clean_key == "SECURE PACKS":
            property_section = "secure"
            continue

        if clean_key == "Quantity":
            if property_section == "secure" and value:
                mapped["secure_pack_quantity"] = value
            continue

        if clean_key in ("Item", "Description", "Color", "Quentity", "Pack ID Number",
                         "Additional ID", "SECURE PACKS"):
            continue

        unmapped.append((f"p2:{clean_key}", value))

    return mapped, unmapped


# ── Main Execution ──

def save_result_excel(doc_key, skew_type, ground_truth, mapped_fields, judge_result, metrics,
                      page1_kvs=None, page2_kvs=None, unmapped=None):
    """Save detailed results to Excel for review."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Field Results"
    ws.append(["Field Name", "Ground Truth", "Extracted Value", "Score", "Reasoning"])

    for eval_item in judge_result.get("field_evaluations", []):
        ws.append([
            eval_item.get("field_name", ""),
            eval_item.get("reference_value", ""),
            eval_item.get("extracted_value", ""),
            eval_item.get("extraction_score", 0),
            eval_item.get("reasoning", ""),
        ])

    # Raw Textract Output tab
    ws_raw = wb.create_sheet("Raw Textract Output")
    ws_raw.append(["Page", "Key", "Value", "Is Checkbox"])
    if page1_kvs:
        for key, value in page1_kvs:
            is_cb = "Yes" if ("SELECTED" in value) else ""
            ws_raw.append([1, key, value, is_cb])
    if page2_kvs:
        for key, value in page2_kvs:
            is_cb = "Yes" if ("SELECTED" in value) else ""
            ws_raw.append([2, key, value, is_cb])

    # Mapped Fields tab
    ws_mapped = wb.create_sheet("Mapped Fields")
    ws_mapped.append(["Field Name", "Extracted Value", "Ground Truth", "Match"])
    for field_name in sorted(set(list(mapped_fields.keys()) + list(ground_truth.keys()))):
        extracted = mapped_fields.get(field_name, "")
        gt = ground_truth.get(field_name, "")
        match = "Yes" if extracted and gt and extracted.lower().strip() == gt.lower().strip() else ("Partial" if extracted and gt else ("Missing" if gt and not extracted else ""))
        ws_mapped.append([field_name, extracted, gt, match])

    # Unmapped Keys tab
    if unmapped:
        ws_unmap = wb.create_sheet("Unmapped Keys")
        ws_unmap.append(["Source", "Key", "Value"])
        for key, value in unmapped:
            ws_unmap.append([key.split(":")[0] if ":" in key else "", key, value])

    # Summary sheet
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Metric", "Value"])
    ws2.append(["Document", doc_key])
    ws2.append(["Skew Type", skew_type])
    ws2.append(["Overall Judge Score", f"{judge_result.get('overall_score', 0):.1%}"])
    ws2.append(["Fields in Ground Truth", metrics.get("fields_in_ground_truth", 0)])
    ws2.append(["Fields Extracted", metrics.get("fields_extracted", 0)])
    ws2.append(["Fields Unmapped", metrics.get("fields_unmapped", 0)])
    ws2.append(["Textract Time (sec)", f"{metrics.get('textract_time', 0):.1f}"])
    ws2.append(["Judge Time (sec)", f"{metrics.get('judge_time', 0):.1f}"])
    ws2.append(["Total Time (sec)", f"{metrics.get('total_time', 0):.1f}"])
    ws2.append(["Textract Pages", metrics.get("pages", 0)])
    ws2.append(["Est. Textract Cost ($)", f"${metrics.get('textract_cost', 0):.4f}"])
    ws2.append(["Summary", judge_result.get("summary", "")])

    excel_dir = os.path.join(RESULTS_DIR, "excel_reports")
    os.makedirs(excel_dir, exist_ok=True)
    safe_key = doc_key.replace("/", "_").replace(" ", "_")
    path = os.path.join(excel_dir, f"{safe_key}_{skew_type}.xlsx")
    wb.save(path)
    return path


def process_document(doc, textract_client, bedrock_client, skew_type="original", image_override=None):
    """Process a single document through Textract + judge.

    Returns result dict with scores, or None on failure.
    """
    doc_key = doc["doc_key"]
    total_start = time.time()
    log.info(f"Processing [{skew_type}]: {doc_key}")

    # Load ground truth
    ground_truth = utils.load_ground_truth(doc["xlsx_path"])
    if not ground_truth:
        log.warning(f"No ground truth for {doc_key}")
        return None

    # Get page images
    if image_override:
        page_images_bytes = image_override
    else:
        try:
            pil_images = utils.pdf_to_images(doc["pdf_path"])
            page_images_bytes = [utils.image_to_bytes(img) for img in pil_images]
        except Exception as e:
            log.error(f"PDF conversion failed for {doc_key}: {e}")
            return None

    # Call Textract for each page — keep per-page KV pairs separate
    per_page_kvs = []
    raw_responses = []
    textract_start = time.time()
    for i, img_bytes in enumerate(page_images_bytes):
        try:
            response = textract_client.analyze_document(
                Document={"Bytes": img_bytes},
                FeatureTypes=["FORMS"],
            )
            raw_responses.append(response)
            page_kvs = parse_textract_kv_pairs(response)
            per_page_kvs.append(page_kvs)
            log.info(f"  Page {i+1}: {len(page_kvs)} key-value pairs extracted")
            time.sleep(0.5)
        except Exception as e:
            log.error(f"  Textract failed on page {i+1}: {e}")
            raw_responses.append({"error": str(e)})
            per_page_kvs.append({})
    textract_time = time.time() - textract_start

    # Save raw response
    raw_dir = os.path.join(RESULTS_DIR, "raw_responses")
    os.makedirs(raw_dir, exist_ok=True)
    safe_key = doc_key.replace("/", "_").replace(" ", "_")
    raw_path = os.path.join(raw_dir, f"{safe_key}_{skew_type}.json")

    def make_serializable(obj):
        if isinstance(obj, bytes):
            return "<bytes>"
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        return obj

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(make_serializable(raw_responses), f, indent=2, default=str)

    # Map to field names — pass page 1 and page 2 separately
    page1_kvs = per_page_kvs[0] if len(per_page_kvs) > 0 else {}
    page2_kvs = per_page_kvs[1] if len(per_page_kvs) > 1 else {}
    mapped_fields, unmapped = map_textract_to_fields(page1_kvs, page2_kvs)
    log.info(f"  {len(mapped_fields)} mapped, {len(unmapped)} unmapped keys")

    # Judge evaluation
    judge_start = time.time()
    judge_result = utils.judge_extraction(ground_truth, mapped_fields, "AWS Textract", bedrock_client)
    judge_time = time.time() - judge_start

    total_time = time.time() - total_start
    num_pages = len(page_images_bytes)
    textract_cost = num_pages * 0.015  # $0.015 per page for Forms

    # Save judge evaluation as JSON
    judge_dir = os.path.join(RESULTS_DIR, "judge_evaluations")
    os.makedirs(judge_dir, exist_ok=True)
    judge_path = os.path.join(judge_dir, f"{safe_key}_{skew_type}.json")
    with open(judge_path, "w", encoding="utf-8") as f:
        json.dump(judge_result, f, indent=2, default=str)

    judge_score = judge_result.get("overall_score", 0.0)
    judge_error = judge_result.get("error", "")

    if judge_error:
        log.warning(f"  Judge error: {judge_error[:100]}")
        return None

    # Save Excel report
    metrics = {
        "fields_in_ground_truth": len(ground_truth),
        "fields_extracted": len(mapped_fields),
        "fields_unmapped": len(unmapped),
        "textract_time": textract_time,
        "judge_time": judge_time,
        "total_time": total_time,
        "pages": num_pages,
        "textract_cost": textract_cost,
    }
    excel_path = save_result_excel(doc_key, skew_type, ground_truth, mapped_fields, judge_result, metrics,
                                   page1_kvs=page1_kvs, page2_kvs=page2_kvs, unmapped=unmapped)

    log.info(f"  Judge score: {judge_score:.1%} | Textract: {textract_time:.1f}s | "
             f"Judge: {judge_time:.1f}s | Cost: ${textract_cost:.3f} | Excel: {os.path.basename(excel_path)}")

    return {
        "doc_key": doc_key,
        "folder": doc["folder"],
        "form_name": doc["form_name"],
        "skew_type": skew_type,
        "judge_score": judge_score,
        "fields_extracted": len(mapped_fields),
        "fields_unmapped": len(unmapped),
        "fields_in_ground_truth": len(ground_truth),
        "textract_time": textract_time,
        "judge_time": judge_time,
        "total_time": total_time,
        "textract_cost": textract_cost,
        "pages": num_pages,
        "judge_summary": judge_result.get("summary", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="AWS Textract Test Runner")
    parser.add_argument("--doc", type=int, help="Run single doc by index (1-based)")
    parser.add_argument("--skew", action="store_true", help="Include skew variants")
    parser.add_argument("--report", action="store_true", help="Print report from saved results")
    parser.add_argument("--loop", action="store_true", help="Run continuously until all done")
    args = parser.parse_args()

    if args.report:
        if os.path.exists(RESULTS_FILE):
            utils.generate_report(RESULTS_FILE, "AWS Textract")
        else:
            print("No results file found. Run tests first.")
        return

    # Initialize clients
    region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
    textract_client = boto3.client("textract", region_name=region)
    bedrock_client = boto3.client("bedrock-runtime", region_name=region)

    # Discover documents
    documents = utils.discover_documents(DOCS_DIR)
    log.info(f"Found {len(documents)} documents")

    if args.doc:
        documents = [documents[args.doc - 1]]

    # Load progress
    progress = utils.load_progress(PROGRESS_FILE)

    # Load existing results
    all_results = []
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r") as f:
            all_results = json.load(f)

    skew_types = ["original"]
    if args.skew:
        skew_types += [name for name, _ in utils.SKEW_TRANSFORMS]

    for doc in documents:
        for skew_type in skew_types:
            result_key = f"{doc['doc_key']}|{skew_type}"
            if result_key in progress["completed"]:
                continue

            # Generate skewed images if needed
            image_override = None
            if skew_type != "original":
                try:
                    pil_images = utils.pdf_to_images(doc["pdf_path"])
                    transform_fn = dict(utils.SKEW_TRANSFORMS)[skew_type]
                    image_override = [transform_fn(utils.image_to_bytes(img)) for img in pil_images]
                except Exception as e:
                    log.error(f"Skew generation failed for {doc['doc_key']}: {e}")
                    continue

            result = process_document(doc, textract_client, bedrock_client,
                                       skew_type=skew_type, image_override=image_override)

            if result:
                progress["completed"][result_key] = True
                all_results.append(result)
                # Save incrementally
                with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, indent=2)
                utils.save_progress(PROGRESS_FILE, progress)
            else:
                progress["failed"][result_key] = progress["failed"].get(result_key, 0) + 1
                utils.save_progress(PROGRESS_FILE, progress)

    log.info(f"Done. {len(all_results)} results saved.")
    if all_results:
        utils.generate_report(RESULTS_FILE, "AWS Textract")


if __name__ == "__main__":
    main()
