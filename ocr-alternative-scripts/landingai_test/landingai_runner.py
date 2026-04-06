"""
Landing.ai test runner.

Uses the Landing.ai Agentic Document Extraction (ADE) API:
  1. Parse: Convert document image to markdown
  2. Extract: Pull structured fields from markdown using schema

Compares extracted fields to ground truth using Claude (Bedrock) as judge.

Usage:
    python landingai_runner.py                  # Run all 60 originals
    python landingai_runner.py --doc 1          # Run single doc (for testing)
    python landingai_runner.py --skew           # Include skew variants
    python landingai_runner.py --report         # Print report from saved results
"""
import os
import sys
import json
import time
import logging
import argparse

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shared_utils as utils

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "landingai.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("landingai_runner")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(SCRIPT_DIR, "..", "..", "Documents")  # Documents folder
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "landingai_progress.json")
RESULTS_FILE = os.path.join(RESULTS_DIR, "landingai_results.json")
SCHEMA_FILE = os.path.join(SCRIPT_DIR, "schema.json")

# ADE API endpoints
ADE_PARSE_URL = "https://api.va.landing.ai/v1/ade/parse"
ADE_EXTRACT_URL = "https://api.va.landing.ai/v1/ade/extract"


# ── Landing.ai API ──

def ade_parse(doc_bytes, api_key, content_type="image/png", filename="page.png"):
    """Parse a document into markdown via Landing.ai ADE Parse API.

    Accepts PNG images or PDF files directly.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                ADE_PARSE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"document": (filename, doc_bytes, content_type)},
                timeout=120,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                log.warning(f"Rate limited on parse, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 3
                log.warning(f"Parse error ({type(e).__name__}), retrying in {wait}s")
                time.sleep(wait)
                continue
            raise


def ade_extract(markdown, schema, api_key):
    """Extract structured fields from markdown via Landing.ai ADE Extract API."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                ADE_EXTRACT_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={
                    "markdown": markdown,
                    "schema": json.dumps(schema) if isinstance(schema, dict) else schema,
                },
                timeout=120,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                log.warning(f"Rate limited on extract, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 3
                log.warning(f"Extract error ({type(e).__name__}), retrying in {wait}s")
                time.sleep(wait)
                continue
            raise


def flatten_extraction(data, prefix=""):
    """Flatten nested Landing.ai extraction response to {field_name: value} dict.

    Maps the nested schema structure back to flat ground truth field names.
    """
    NESTED_TO_FLAT = {
        "arresting_officer.officer_type": "officer_type",
        "arresting_officer.last_name": "officer_last_name",
        "arresting_officer.first_name": "officer_first_name",
        "officer_contact_details.id_number_1": "badge_number",
        "officer_contact_details.id_number_2": "employee_id_number",
        "officer_contact_details.phone_number": "contact_phone_number",
        "officer_contact_details.agency": "agency",
        "prisoner_personal_information.first_name": "first_name",
        "prisoner_personal_information.last_name": "last_name",
        "prisoner_personal_information.middle_name": "middle_name",
        "prisoner_demographics.social_security_number": "ssn",
        "prisoner_demographics.date_of_birth": "date_of_birth",
        "prisoner_demographics.age": "age",
        "prisoner_demographics.sex": "sex",
        "prisoner_origin.race": "race",
        "prisoner_origin.ethnicity": "ethnicity",
        "prisoner_origin.citizenship": "citizenship",
        "prisoner_origin.country_of_birth": "country_of_birth",
        "prisoner_birth_city.city_of_birth": "city_of_birth",
        "prisoner_physical_attributes.height": "height",
        "prisoner_physical_attributes.weight": "weight",
        "prisoner_physical_attributes.eyes": "eyes",
        "prisoner_physical_attributes.skin": "skin",
        "prisoner_hair_details.hair_type": "hair_type",
        "prisoner_hair_details.hair_length": "hair_length",
        "prisoner_hair_details.hair_color": "hair_color",
        "prisoner_facial_features.build": "build",
        "prisoner_facial_features.beard": "beard",
        "prisoner_facial_features.mustache": "mustache",
        "prisoner_facial_features.glasses": "glasses",
        "prisoner_status_and_habits.marital_status": "marital_status",
        "prisoner_status_and_habits.religious_preference": "religious_preference",
        "prisoner_status_and_habits.veteran": "veteran",
        "prisoner_status_and_habits.using_drugs": "using_drugs",
        "prisoner_alcohol_and_wanted_status.using_alcohol": "using_alcohol",
        "prisoner_alcohol_and_wanted_status.wanted": "wanted",
        "prisoner_alcohol_and_wanted_status.agency_wanting_person": "agency_wanting_person",
        "prisoner_alcohol_and_wanted_status.agency_contact_person": "agency_contact_person",
        "additional_identifiers.hcso_spn": "hcso_spn",
        "additional_identifiers.state_issued_id_number": "state_issued_id_number",
        "additional_identifiers.issuing_state": "issuing_state",
        "additional_identifiers.drivers_license_number": "drivers_license_number",
        "drivers_license_details.dl_state": "dl_state",
        "drivers_license_details.dl_type": "dl_type",
        "drivers_license_details.sid_number": "sid_number",
        "drivers_license_details.fbi_number": "fbi_number",
        "other_identification_numbers.afis_number": "afis_number",
        "other_identification_numbers.so_number": "so_number",
        "other_identification_numbers.da_log_number": "da_log_number",
        "other_identification_numbers.assistant_da_name": "assistant_da_name",
        "home_address.address_type": "address_type",
        "home_address.street": "address_street",
        "home_address.city": "address_city",
        "home_address.state": "address_state",
        "home_address.zip_code": "address_zip",
        "home_address_source.source": "address_source",
        "cell_phone.phone_type": "phone_1_type",
        "cell_phone.number": "phone_1_number",
        "cell_phone.source": "phone_1_source",
        "secondary_phone.phone_type": "phone_2_type",
        "secondary_phone.number": "phone_2_number",
        "secondary_phone.source": "phone_2_source",
        "emergency_contact.first_name": "emergency_first_name",
        "emergency_contact.middle_name": "emergency_middle_name",
        "emergency_contact.last_name": "emergency_last_name",
        "emergency_contact.relationship": "emergency_relationship",
        "emergency_contact_details.phone_number": "emergency_phone",
        "emergency_contact_details.source": "emergency_source",
        "employer_information.employer_name": "employer_name",
        "employer_information.occupation": "occupation",
        "employer_information.employer_street_address": "employer_address",
        "employer_contact_details.city": "employer_city",
        "employer_contact_details.state": "employer_state",
        "employer_contact_details.zip_code": "employer_zip",
        "employer_contact_details.phone_type": "employer_phone_type",
        "employer_contact_details.work_phone": "employer_phone",
        "employer_source.source": "employer_source",
        "arrest_information.date": "arrest_date",
        "arrest_information.time": "arrest_time",
        "arrest_information.arrest_location": "arrest_location",
        "arrest_information.arresting_agency": "arresting_agency",
        "prisoner_health_and_behavior.prisoner_health_condition": "prisoner_health_condition",
        "prisoner_health_and_behavior.unusual_behavior": "unusual_behavior",
        "arresting_officer_details_arrest_info.last_name": "arr_officer_last_name",
        "arresting_officer_details_arrest_info.first_name": "arr_officer_first_name",
        "arresting_officer_details_arrest_info.badge_number": "arr_officer_badge",
        "arresting_officer_details_arrest_info.employee_id_number": "arr_officer_employee_id",
        "arresting_officer_contact_and_unit.contact_number": "arr_officer_contact",
        "arresting_officer_contact_and_unit.unit_number": "arr_officer_unit",
        "arresting_officer_contact_and_unit.arresting_agency": "arr_officer_agency",
        "transporting_officer_details.last_name": "trans_officer_last_name",
        "transporting_officer_details.first_name": "trans_officer_first_name",
        "transporting_officer_details.badge_number": "trans_officer_badge",
        "transporting_officer_details.employee_id_number": "trans_officer_employee_id",
        "transporting_officer_contact_and_unit.contact_number": "trans_officer_contact",
        "transporting_officer_contact_and_unit.unit_number": "trans_officer_unit",
        "transporting_officer_contact_and_unit.agency": "trans_officer_agency",
        "secure_packs.quantity": "secure_pack_quantity",
        "secure_packs.prisoner_given_opportunity_for_phone_numbers": "phone_numbers_opportunity",
        "signatures.prisoner_signature": "prisoner_signature",
        "signatures.officer_signature": "officer_signature",
        "ccq_info.ccq_run": "ccq_run",
    }

    flat = {}

    def _recurse(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _recurse(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            # Handle arrays (tattoos, property, etc.)
            if path in ("tattoos", "scars_marks_tattoos"):
                for i, item in enumerate(obj):
                    if isinstance(item, dict):
                        idx = i + 1
                        if item.get("type"):
                            flat[f"smt_{idx}_type"] = str(item["type"])
                        if item.get("location"):
                            flat[f"smt_{idx}_location"] = str(item["location"])
                        if item.get("description"):
                            flat[f"smt_{idx}_description"] = str(item["description"])
            elif path in ("valuable_property", "clothing_property", "other_property"):
                flat[path] = json.dumps(obj) if obj else ""
            elif path in ("processing_flows", "prisoner_flags"):
                flat[path] = ", ".join(str(x) for x in obj if x) if obj else ""
        else:
            full_path = path
            if full_path in NESTED_TO_FLAT:
                value = str(obj).strip() if obj is not None else ""
                if value:
                    flat[NESTED_TO_FLAT[full_path]] = value
            # Also store under the raw path for debugging

    _recurse(data, "")
    return flat


def save_result_excel(doc_key, skew_type, ground_truth, mapped_fields, judge_result, metrics,
                      raw_response=None):
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

    # Raw Landing.ai Output tab
    ws_raw = wb.create_sheet("Raw Landing.ai Output")
    ws_raw.append(["Section", "Field", "Value"])
    if raw_response:
        extraction = raw_response.get("extraction", raw_response)
        def _write_nested(obj, section=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _write_nested(v, f"{section}.{k}" if section else k)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _write_nested(item, f"{section}[{i}]")
            else:
                parts = section.rsplit(".", 1)
                sec = parts[0] if len(parts) > 1 else ""
                field = parts[-1]
                ws_raw.append([sec, field, str(obj) if obj is not None else ""])
        _write_nested(extraction)

    # Mapped Fields tab
    ws_mapped = wb.create_sheet("Mapped Fields")
    ws_mapped.append(["Field Name", "Extracted Value", "Ground Truth", "Match"])
    for field_name in sorted(set(list(mapped_fields.keys()) + list(ground_truth.keys()))):
        extracted = mapped_fields.get(field_name, "")
        gt = ground_truth.get(field_name, "")
        match = "Yes" if extracted and gt and extracted.lower().strip() == gt.lower().strip() else (
            "Partial" if extracted and gt else ("Missing" if gt and not extracted else ""))
        ws_mapped.append([field_name, extracted, gt, match])

    # Summary sheet
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Metric", "Value"])
    ws2.append(["Document", doc_key])
    ws2.append(["Skew Type", skew_type])
    ws2.append(["Overall Judge Score", f"{judge_result.get('overall_score', 0):.1%}"])
    ws2.append(["Fields in Ground Truth", metrics.get("fields_in_ground_truth", 0)])
    ws2.append(["Fields Extracted", metrics.get("fields_extracted", 0)])
    ws2.append(["Parse Time (sec)", f"{metrics.get('parse_time', 0):.1f}"])
    ws2.append(["Extract Time (sec)", f"{metrics.get('extract_time', 0):.1f}"])
    ws2.append(["Judge Time (sec)", f"{metrics.get('judge_time', 0):.1f}"])
    ws2.append(["Total Time (sec)", f"{metrics.get('total_time', 0):.1f}"])
    ws2.append(["Pages", metrics.get("pages", 0)])
    ws2.append(["Est. Landing.ai Cost ($)", f"${metrics.get('landing_cost', 0):.4f}"])
    ws2.append(["Summary", judge_result.get("summary", "")])

    excel_dir = os.path.join(RESULTS_DIR, "excel_reports")
    os.makedirs(excel_dir, exist_ok=True)
    safe_key = doc_key.replace("/", "_").replace(" ", "_")
    path = os.path.join(excel_dir, f"{safe_key}_{skew_type}.xlsx")
    wb.save(path)
    return path


# ── Main Execution ──

def process_document(doc, api_key, bedrock_client, schema, skew_type="original", image_override=None):
    """Process a single document through Landing.ai + judge."""
    doc_key = doc["doc_key"]
    total_start = time.time()
    log.info(f"Processing [{skew_type}]: {doc_key}")

    # Load ground truth
    ground_truth = utils.load_ground_truth(doc["xlsx_path"])
    if not ground_truth:
        log.warning(f"No ground truth for {doc_key}")
        return None

    # Step 1: Parse document to markdown
    all_markdown = []
    parse_start = time.time()
    num_pages = 0

    if image_override:
        # Skew mode: send individual page images
        num_pages = len(image_override)
        for i, img_bytes in enumerate(image_override):
            try:
                parse_resp = ade_parse(img_bytes, api_key)
                markdown = parse_resp.get("markdown", "")
                all_markdown.append(markdown)
                log.info(f"  Page {i+1}: parsed ({len(markdown)} chars markdown)")
                time.sleep(1)
            except Exception as e:
                log.error(f"  Landing.ai parse failed on page {i+1}: {e}")
                all_markdown.append("")
    else:
        # Original mode: send PDF directly (better quality)
        try:
            with open(doc["pdf_path"], "rb") as f:
                pdf_bytes = f.read()
            parse_resp = ade_parse(pdf_bytes, api_key, content_type="application/pdf", filename=os.path.basename(doc["pdf_path"]))
            markdown = parse_resp.get("markdown", "")
            all_markdown.append(markdown)
            # Count pages from PDF
            import fitz
            pdf_doc = fitz.open(doc["pdf_path"])
            num_pages = len(pdf_doc)
            pdf_doc.close()
            log.info(f"  PDF parsed directly ({len(markdown)} chars markdown, {num_pages} pages)")
        except Exception as e:
            log.error(f"  Landing.ai parse failed: {e}")
            # Fallback to page images
            log.info(f"  Falling back to page-by-page parsing...")
            try:
                pil_images = utils.pdf_to_images(doc["pdf_path"])
                num_pages = len(pil_images)
                for i, img in enumerate(pil_images):
                    img_bytes = utils.image_to_bytes(img)
                    parse_resp = ade_parse(img_bytes, api_key)
                    markdown = parse_resp.get("markdown", "")
                    all_markdown.append(markdown)
                    log.info(f"  Page {i+1}: parsed ({len(markdown)} chars markdown)")
                    time.sleep(1)
            except Exception as e2:
                log.error(f"  Fallback also failed: {e2}")
                all_markdown.append("")
    parse_time = time.time() - parse_start

    combined_markdown = "\n\n---\n\n".join(all_markdown)

    # Step 2: Extract structured fields from combined markdown
    extract_start = time.time()
    raw_response = {}
    try:
        raw_response = ade_extract(combined_markdown, schema, api_key)
        log.info(f"  Extract: got response")
    except Exception as e:
        log.error(f"  Landing.ai extract failed: {e}")
        raw_response = {"error": str(e)}
    extract_time = time.time() - extract_start

    # Include markdown in raw response for debugging
    raw_response["_parsed_markdown"] = combined_markdown

    # Save raw response
    raw_dir = os.path.join(RESULTS_DIR, "raw_responses")
    os.makedirs(raw_dir, exist_ok=True)
    safe_key = doc_key.replace("/", "_").replace(" ", "_")
    raw_path = os.path.join(raw_dir, f"{safe_key}_{skew_type}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_response, f, indent=2, default=str)

    # Flatten nested response to field names
    extraction_data = raw_response.get("extraction", raw_response)
    mapped_fields = flatten_extraction(extraction_data)
    log.info(f"  {len(mapped_fields)} fields extracted")

    # Judge evaluation
    judge_start = time.time()
    judge_result = utils.judge_extraction(ground_truth, mapped_fields, "Landing.ai", bedrock_client)
    judge_time = time.time() - judge_start

    total_time = time.time() - total_start
    num_pages = num_pages or 2  # default to 2 pages if not counted
    # Estimate: ~3 credits/page parse + ~2 credits extract = ~5 credits/page * $0.01/credit
    landing_cost = num_pages * 5 * 0.01

    # Save judge evaluation
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
        "parse_time": parse_time,
        "extract_time": extract_time,
        "judge_time": judge_time,
        "total_time": total_time,
        "pages": num_pages,
        "landing_cost": landing_cost,
    }
    excel_path = save_result_excel(doc_key, skew_type, ground_truth, mapped_fields, judge_result, metrics,
                                   raw_response=raw_response)

    log.info(f"  Judge score: {judge_score:.1%} | Parse: {parse_time:.1f}s | "
             f"Extract: {extract_time:.1f}s | Judge: {judge_time:.1f}s | "
             f"Cost: ${landing_cost:.3f} | Excel: {os.path.basename(excel_path)}")

    return {
        "doc_key": doc_key,
        "folder": doc["folder"],
        "form_name": doc["form_name"],
        "skew_type": skew_type,
        "judge_score": judge_score,
        "fields_extracted": len(mapped_fields),
        "fields_in_ground_truth": len(ground_truth),
        "parse_time": parse_time,
        "extract_time": extract_time,
        "judge_time": judge_time,
        "total_time": total_time,
        "landing_cost": landing_cost,
        "pages": num_pages,
        "judge_summary": judge_result.get("summary", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="Landing.ai Test Runner")
    parser.add_argument("--doc", type=int, help="Run single doc by index (1-based)")
    parser.add_argument("--skew", action="store_true", help="Include skew variants")
    parser.add_argument("--report", action="store_true", help="Print report from saved results")
    args = parser.parse_args()

    if args.report:
        if os.path.exists(RESULTS_FILE):
            utils.generate_report(RESULTS_FILE, "Landing.ai")
        else:
            print("No results file found. Run tests first.")
        return

    # Check API key
    api_key = os.environ.get("LANDING_AI_API_KEY")
    if not api_key:
        print("ERROR: Set LANDING_AI_API_KEY environment variable")
        print("  PowerShell: $env:LANDING_AI_API_KEY = 'your-key'")
        print("  Bash: export LANDING_AI_API_KEY='your-key'")
        sys.exit(1)

    # Load schema
    with open(SCHEMA_FILE, "r") as f:
        schema = json.load(f)
    log.info(f"Loaded schema with {len(schema.get('properties', {}))} top-level sections")

    # Initialize Bedrock client for judging
    import boto3
    bedrock_client = boto3.client("bedrock-runtime",
                                   region_name=os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

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

            result = process_document(doc, api_key, bedrock_client, schema,
                                       skew_type=skew_type, image_override=image_override)

            if result:
                progress["completed"][result_key] = True
                all_results.append(result)
                with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, indent=2)
                utils.save_progress(PROGRESS_FILE, progress)
            else:
                progress["failed"][result_key] = progress["failed"].get(result_key, 0) + 1
                utils.save_progress(PROGRESS_FILE, progress)

    log.info(f"Done. {len(all_results)} results saved.")
    if all_results:
        utils.generate_report(RESULTS_FILE, "Landing.ai")


if __name__ == "__main__":
    main()
