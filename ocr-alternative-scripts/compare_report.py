"""
Cross-system comparison report.

Combines results from Textract, Landing.ai, and optionally the Bedrock models
into a unified comparison table.

Usage:
    python compare_report.py
"""
import os
import sys
import json
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEXTRACT_RESULTS = os.path.join(SCRIPT_DIR, "textract_test", "results", "textract_results.json")
LANDINGAI_RESULTS = os.path.join(SCRIPT_DIR, "landingai_test", "results", "landingai_results.json")


def load_results(path, system_name):
    """Load results JSON and tag with system name."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        results = json.load(f)
    for r in results:
        r["system"] = system_name
    return results


def load_bedrock_results():
    """Load Bedrock results from Firestore (optional)."""
    try:
        from google.cloud import firestore
        db = firestore.Client(project="ecourtdateocr")

        sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
        from orchestrator import ALL_BATCH_IDS

        test_runs = {}
        for doc in db.collection("test_runs").stream():
            tr = doc.to_dict()
            if tr.get("status") == "completed" and "_bedrock" in tr.get("ocr_library", ""):
                test_runs[doc.id] = tr

        results = []
        for tr_id, tr in test_runs.items():
            model = tr.get("ocr_library", "unknown")
            for rdoc in db.collection("results").where("test_run_id", "==", tr_id).stream():
                r = rdoc.to_dict()
                batch_id = r.get("batch_id", "")
                skew_type = "original" if batch_id in ALL_BATCH_IDS else "skew"
                judge_score = r.get("judge_overall_score", 0)
                if judge_score and judge_score > 0:
                    results.append({
                        "system": model.replace("_bedrock", ""),
                        "skew_type": skew_type,
                        "judge_score": judge_score,
                    })
        return results
    except Exception as e:
        print(f"Could not load Bedrock results: {e}")
        return []


def main():
    all_results = []
    all_results.extend(load_results(TEXTRACT_RESULTS, "AWS Textract"))
    all_results.extend(load_results(LANDINGAI_RESULTS, "Landing.ai"))

    # Optionally include Bedrock
    bedrock = load_bedrock_results()
    all_results.extend(bedrock)

    if not all_results:
        print("No results found.")
        return

    # Group by system + skew_type
    grouped = defaultdict(list)
    for r in all_results:
        key = (r["system"], r.get("skew_type", "original"))
        grouped[key].append(r)

    # Get all systems
    systems = sorted(set(r["system"] for r in all_results))

    # ── Originals Table ──
    print("\n" + "=" * 70)
    print("ORIGINALS — ranked by Judge Score (all systems)")
    print("=" * 70)

    originals = []
    for system in systems:
        records = grouped.get((system, "original"), [])
        if not records:
            continue
        scores = [r["judge_score"] for r in records if r.get("judge_score")]
        if not scores:
            continue
        originals.append({
            "system": system,
            "docs": len(records),
            "judge": sum(scores) / len(scores) * 100,
        })

    originals.sort(key=lambda x: x["judge"], reverse=True)
    print(f"\n{'System':<25} {'Docs':>5} {'Judge':>8}")
    print("-" * 40)
    for o in originals:
        print(f"{o['system']:<25} {o['docs']:>5} {o['judge']:>7.1f}%")

    # ── Degradation Table ──
    skew_order = ["original", "light_skew", "heavy_skew", "180_clean", "180_degraded"]
    skew_labels = {
        "original": "Original",
        "light_skew": "Light skew",
        "heavy_skew": "Heavy skew",
        "180_clean": "180° clean",
        "180_degraded": "180° degraded",
    }

    has_skews = any(r.get("skew_type", "original") != "original" for r in all_results)
    if has_skews:
        print("\n" + "=" * 70)
        print("DEGRADATION RESILIENCE — Judge Score by skew type")
        print("=" * 70)

        # Only show systems that have skew data
        skew_systems = [s for s in systems if any(
            grouped.get((s, sk)) for sk in skew_order[1:]
        )]
        if not skew_systems:
            skew_systems = systems[:5]  # Fallback

        header = f"{'Skew':<16}" + "".join(f"{s[:12]:>14}" for s in skew_systems)
        print(f"\n{header}")
        print("-" * (16 + 14 * len(skew_systems)))

        for skew in skew_order:
            row = f"{skew_labels.get(skew, skew):<16}"
            for system in skew_systems:
                records = grouped.get((system, skew), [])
                scores = [r["judge_score"] for r in records if r.get("judge_score")]
                if scores:
                    avg = sum(scores) / len(scores) * 100
                    row += f"{avg:>13.0f}%"
                else:
                    row += f"{'N/A':>14}"
            print(row)

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    main()
