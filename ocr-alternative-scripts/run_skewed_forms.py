"""
Run Textract and/or Landing.ai on pre-generated skewed forms.

Processes documents from Documents/skewed_forms/{originals,180_clean,heavy_skew}

Usage:
    python run_skewed_forms.py --textract              # Run Textract on all variants
    python run_skewed_forms.py --landingai              # Run Landing.ai on all variants
    python run_skewed_forms.py --textract --landingai   # Run both
    python run_skewed_forms.py --report                 # Print comparison report
"""
import os
import sys
import json
import time
import glob
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_utils as utils

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "run_skewed.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("run_skewed")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKEWED_DIR = os.path.join(SCRIPT_DIR, "..", "Documents", "skewed_forms")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "skewed_results")
TEXTRACT_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "skewed_progress_textract.json")
LANDINGAI_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "skewed_progress_landingai.json")


def discover_skewed_docs():
    """Find all documents in the skewed_forms directory structure.

    Returns list of dicts: [{doc_name, skew_type, xlsx_path, image_paths or pdf_path}, ...]
    """
    documents = []

    for skew_type in ["originals", "180_clean", "heavy_skew"]:
        skew_dir = os.path.join(SKEWED_DIR, skew_type)
        if not os.path.isdir(skew_dir):
            log.warning(f"Skew dir not found: {skew_dir}")
            continue

        xlsx_files = sorted(glob.glob(os.path.join(skew_dir, "*.xlsx")))
        for xlsx_path in xlsx_files:
            doc_name = os.path.splitext(os.path.basename(xlsx_path))[0]

            if skew_type == "originals":
                # Original PDFs
                pdf_path = os.path.join(skew_dir, f"{doc_name}.pdf")
                if os.path.exists(pdf_path):
                    documents.append({
                        "doc_name": doc_name,
                        "skew_type": "original",
                        "xlsx_path": xlsx_path,
                        "pdf_path": pdf_path,
                        "image_paths": None,
                    })
            else:
                # Skewed PNGs (page1, page2)
                page_files = sorted(glob.glob(os.path.join(skew_dir, f"{doc_name}_page*.png")))
                if page_files:
                    documents.append({
                        "doc_name": doc_name,
                        "skew_type": skew_type,
                        "xlsx_path": xlsx_path,
                        "pdf_path": None,
                        "image_paths": page_files,
                    })

    return documents


def run_textract(doc, bedrock_client, progress, all_results):
    """Run Textract on a single document."""
    import boto3
    textract_client = boto3.client("textract",
                                    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

    sys.path.insert(0, os.path.join(SCRIPT_DIR, "textract_test"))
    from textract_runner import parse_textract_kv_pairs, map_textract_to_fields, save_result_excel

    result_key = f"textract|{doc['doc_name']}|{doc['skew_type']}"
    if result_key in progress["completed"]:
        return

    doc_name = doc["doc_name"]
    skew_type = doc["skew_type"]
    total_start = time.time()
    log.info(f"[Textract] [{skew_type}] {doc_name}")

    ground_truth = utils.load_ground_truth(doc["xlsx_path"])
    if not ground_truth:
        return

    # Get page images
    if doc["pdf_path"]:
        pil_images = utils.pdf_to_images(doc["pdf_path"])
        page_images = [utils.image_to_bytes(img) for img in pil_images]
    else:
        page_images = []
        for p in doc["image_paths"]:
            with open(p, "rb") as fh:
                page_images.append(fh.read())

    # Call Textract
    per_page_kvs = []
    textract_start = time.time()
    for i, img_bytes in enumerate(page_images):
        try:
            response = textract_client.analyze_document(
                Document={"Bytes": img_bytes},
                FeatureTypes=["FORMS"],
            )
            page_kvs = parse_textract_kv_pairs(response)
            per_page_kvs.append(page_kvs)
            log.info(f"  Page {i+1}: {len(page_kvs)} KV pairs")
            time.sleep(0.5)
        except Exception as e:
            log.error(f"  Textract page {i+1} failed: {e}")
            per_page_kvs.append([])
    textract_time = time.time() - textract_start

    page1_kvs = per_page_kvs[0] if len(per_page_kvs) > 0 else []
    page2_kvs = per_page_kvs[1] if len(per_page_kvs) > 1 else []
    mapped_fields, unmapped = map_textract_to_fields(page1_kvs, page2_kvs)

    # Judge
    judge_start = time.time()
    judge_result = utils.judge_extraction(ground_truth, mapped_fields, "AWS Textract", bedrock_client)
    judge_time = time.time() - judge_start

    total_time = time.time() - total_start
    judge_score = judge_result.get("overall_score", 0.0)
    judge_error = judge_result.get("error", "")

    if judge_error:
        log.warning(f"  Judge error: {judge_error[:100]}")
        return

    # Save results
    results_subdir = os.path.join(RESULTS_DIR, "textract")
    os.makedirs(results_subdir, exist_ok=True)
    judge_path = os.path.join(results_subdir, f"{doc_name}_{skew_type}.json")
    with open(judge_path, "w", encoding="utf-8") as f:
        json.dump(judge_result, f, indent=2, default=str)

    log.info(f"  Score: {judge_score:.1%} | Textract: {textract_time:.1f}s | Judge: {judge_time:.1f}s")

    result = {
        "system": "AWS Textract",
        "doc_name": doc_name,
        "skew_type": skew_type,
        "judge_score": judge_score,
        "textract_time": textract_time,
        "judge_time": judge_time,
        "total_time": total_time,
    }
    progress["completed"][result_key] = True
    all_results.append(result)


def run_landingai(doc, api_key, bedrock_client, schema, progress, all_results):
    """Run Landing.ai on a single document."""
    sys.path.insert(0, os.path.join(SCRIPT_DIR, "landingai_test"))
    from landingai_runner import ade_parse, ade_extract, flatten_extraction

    result_key = f"landingai|{doc['doc_name']}|{doc['skew_type']}"
    if result_key in progress["completed"]:
        return

    doc_name = doc["doc_name"]
    skew_type = doc["skew_type"]
    total_start = time.time()
    log.info(f"[Landing.ai] [{skew_type}] {doc_name}")

    ground_truth = utils.load_ground_truth(doc["xlsx_path"])
    if not ground_truth:
        return

    # Parse
    parse_start = time.time()
    all_markdown = []

    if doc["pdf_path"]:
        # Send PDF directly
        try:
            with open(doc["pdf_path"], "rb") as f:
                pdf_bytes = f.read()
            parse_resp = ade_parse(pdf_bytes, api_key, content_type="application/pdf",
                                   filename=os.path.basename(doc["pdf_path"]))
            markdown = parse_resp.get("markdown", "")
            all_markdown.append(markdown)
            log.info(f"  PDF parsed ({len(markdown)} chars)")
        except Exception as e:
            log.error(f"  Parse failed: {e}")
            return
    else:
        # Send page images
        for i, img_path in enumerate(doc["image_paths"]):
            try:
                with open(img_path, "rb") as f:
                    img_bytes = f.read()
                parse_resp = ade_parse(img_bytes, api_key)
                markdown = parse_resp.get("markdown", "")
                all_markdown.append(markdown)
                log.info(f"  Page {i+1} parsed ({len(markdown)} chars)")
                time.sleep(1)
            except Exception as e:
                log.error(f"  Parse page {i+1} failed: {e}")
                all_markdown.append("")
    parse_time = time.time() - parse_start

    combined_markdown = "\n\n---\n\n".join(all_markdown)

    # Extract
    extract_start = time.time()
    try:
        raw_response = ade_extract(combined_markdown, schema, api_key)
    except Exception as e:
        log.error(f"  Extract failed: {e}")
        return
    extract_time = time.time() - extract_start

    extraction_data = raw_response.get("extraction", raw_response)
    mapped_fields = flatten_extraction(extraction_data)
    log.info(f"  {len(mapped_fields)} fields extracted")

    # Judge
    judge_start = time.time()
    judge_result = utils.judge_extraction(ground_truth, mapped_fields, "Landing.ai", bedrock_client)
    judge_time = time.time() - judge_start

    total_time = time.time() - total_start
    judge_score = judge_result.get("overall_score", 0.0)
    judge_error = judge_result.get("error", "")

    if judge_error:
        log.warning(f"  Judge error: {judge_error[:100]}")
        return

    # Save results
    results_subdir = os.path.join(RESULTS_DIR, "landingai")
    os.makedirs(results_subdir, exist_ok=True)
    judge_path = os.path.join(results_subdir, f"{doc_name}_{skew_type}.json")
    with open(judge_path, "w", encoding="utf-8") as f:
        json.dump(judge_result, f, indent=2, default=str)

    log.info(f"  Score: {judge_score:.1%} | Parse: {parse_time:.1f}s | Extract: {extract_time:.1f}s | Judge: {judge_time:.1f}s")

    result = {
        "system": "Landing.ai",
        "doc_name": doc_name,
        "skew_type": skew_type,
        "judge_score": judge_score,
        "parse_time": parse_time,
        "extract_time": extract_time,
        "judge_time": judge_time,
        "total_time": total_time,
    }
    progress["completed"][result_key] = True
    all_results.append(result)


def print_report(all_results):
    """Print comparison report."""
    from collections import defaultdict

    if not all_results:
        print("No results.")
        return

    grouped = defaultdict(list)
    for r in all_results:
        grouped[(r["system"], r["skew_type"])].append(r)

    systems = sorted(set(r["system"] for r in all_results))
    skew_order = ["original", "180_clean", "heavy_skew"]
    skew_labels = {"original": "Original", "180_clean": "180° Upside-down", "heavy_skew": "Heavy Skew"}

    print(f"\n{'=' * 70}")
    print("COMPARISON REPORT — Skewed Forms")
    print(f"{'=' * 70}")

    # Summary table
    header = f"{'Skew Type':<22}" + "".join(f"{s:>20}" for s in systems)
    print(f"\n{header}")
    print("-" * (22 + 20 * len(systems)))

    for skew in skew_order:
        row = f"{skew_labels.get(skew, skew):<22}"
        for system in systems:
            records = grouped.get((system, skew), [])
            if records:
                scores = [r["judge_score"] for r in records]
                avg = sum(scores) / len(scores) * 100
                row += f"{avg:>15.1f}% ({len(records)})"
            else:
                row += f"{'N/A':>20}"
        print(row)

    # Per-document detail
    for skew in skew_order:
        print(f"\n--- {skew_labels.get(skew, skew)} ---")
        print(f"{'Document':<35}" + "".join(f"{s:>20}" for s in systems))
        print("-" * (35 + 20 * len(systems)))

        all_docs = sorted(set(r["doc_name"] for r in all_results if r["skew_type"] == skew))
        for doc_name in all_docs:
            row = f"{doc_name:<35}"
            for system in systems:
                matches = [r for r in all_results
                          if r["system"] == system and r["doc_name"] == doc_name and r["skew_type"] == skew]
                if matches:
                    row += f"{matches[0]['judge_score']*100:>19.1f}%"
                else:
                    row += f"{'—':>20}"
            print(row)

    print(f"\n{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(description="Run Textract/Landing.ai on pre-generated skewed forms")
    parser.add_argument("--textract", action="store_true", help="Run Textract")
    parser.add_argument("--landingai", action="store_true", help="Run Landing.ai")
    parser.add_argument("--report", action="store_true", help="Print report from saved results")
    args = parser.parse_args()

    if args.report:
        # Reconstruct results from judge evaluation files for report
        import glob as g
        all_results = []
        for system, subdir in [('AWS Textract', 'textract'), ('Landing.ai', 'landingai')]:
            for jf in sorted(g.glob(os.path.join(RESULTS_DIR, subdir, '*.json'))):
                name = os.path.splitext(os.path.basename(jf))[0]
                if '_original' in name:
                    doc_name = name.rsplit('_original', 1)[0]
                    skew_type = 'original'
                elif '_180_clean' in name:
                    doc_name = name.rsplit('_180_clean', 1)[0]
                    skew_type = '180_clean'
                elif '_heavy_skew' in name:
                    doc_name = name.rsplit('_heavy_skew', 1)[0]
                    skew_type = 'heavy_skew'
                else:
                    continue
                with open(jf) as f:
                    judge = json.load(f)
                evals = judge.get('field_evaluations', [])
                scores = [e.get('extraction_score', 0) for e in evals if e.get('extraction_score') is not None]
                score = sum(scores) / len(scores) if scores else 0
                all_results.append({'system': system, 'doc_name': doc_name, 'skew_type': skew_type, 'judge_score': score})
        print_report(all_results)
        return

    if not args.textract and not args.landingai:
        print("Specify --textract, --landingai, or both. Use --report to see results.")
        return

    # Discover documents
    documents = discover_skewed_docs()
    log.info(f"Found {len(documents)} document variants")
    for skew in ["original", "180_clean", "heavy_skew"]:
        count = len([d for d in documents if d["skew_type"] == skew])
        log.info(f"  {skew}: {count} docs")

    # Initialize Bedrock client for judging
    import boto3
    bedrock_client = boto3.client("bedrock-runtime",
                                   region_name=os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

    # Run Textract (separate progress file)
    if args.textract:
        progress = utils.load_progress(TEXTRACT_PROGRESS_FILE)
        all_results = []
        log.info("=== Running Textract ===")
        for doc in documents:
            try:
                run_textract(doc, bedrock_client, progress, all_results)
                utils.save_progress(TEXTRACT_PROGRESS_FILE, progress)
            except Exception as e:
                log.error(f"Textract error on {doc['doc_name']}: {e}")

    # Run Landing.ai (separate progress file)
    if args.landingai:
        api_key = os.environ.get("LANDING_AI_API_KEY")
        if not api_key:
            print("ERROR: Set LANDING_AI_API_KEY environment variable")
            return

        schema_file = os.path.join(SCRIPT_DIR, "landingai_test", "schema.json")
        with open(schema_file, "r") as f:
            schema = json.load(f)

        progress = utils.load_progress(LANDINGAI_PROGRESS_FILE)
        all_results = []
        log.info("=== Running Landing.ai ===")
        for doc in documents:
            try:
                run_landingai(doc, api_key, bedrock_client, schema, progress, all_results)
                utils.save_progress(LANDINGAI_PROGRESS_FILE, progress)
            except Exception as e:
                log.error(f"Landing.ai error on {doc['doc_name']}: {e}")

    log.info("Done.")


if __name__ == "__main__":
    main()
