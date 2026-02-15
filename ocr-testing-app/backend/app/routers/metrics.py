"""
Metrics and analytics routes.
"""
import io
import csv
from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List

from app.auth.dependencies import get_current_user_id
from app.services.firestore import FirestoreService

router = APIRouter()


@router.get("/matrix")
async def get_matrix_data(
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Return denormalized data for building Layout x OCR matrices.
    Each row represents one document result with its test run metadata.
    The frontend handles filtering and aggregation.
    """
    firestore = FirestoreService()

    # Get all completed test runs
    test_runs = await firestore.list_test_runs()
    completed_runs = [tr for tr in test_runs if tr.status.value == "completed"]

    if not completed_runs:
        return {"rows": [], "filters": {
            "users": [], "dates": [], "batches": [], "batch_jobs": [],
            "batch_types": [], "fields": [], "test_runs": [], "documents": [],
            "prompts": [],
        }}

    # Get all batches for type info
    batches = await firestore.list_batches()
    batch_map = {b.id: b for b in batches}

    # Build batch job lookup for grouping runs by job
    batch_jobs = await firestore.list_batch_jobs()
    batch_job_map = {bj.id: bj for bj in batch_jobs}

    rows = []
    users_set = set()
    dates_set = set()
    batches_set = set()
    batch_types_set = set()
    fields_set = set()
    test_runs_list = []
    documents_set = set()
    batch_jobs_set = set()
    prompts_set = set()

    vlm_engines = {"got_ocr", "mineru"}

    for tr in completed_runs:
        # Skip VLM engines — they don't use layout detection
        if tr.ocr_library in vlm_engines:
            continue

        # Duration in seconds
        duration_s = None
        if tr.started_at and tr.completed_at:
            duration_s = round((tr.completed_at - tr.started_at).total_seconds(), 1)

        results = await firestore.get_results_by_test_run(tr.id)

        # Collect batch type info
        batch_type = "synthetic"
        for bid in tr.batch_ids:
            b = batch_map.get(bid)
            if b:
                batch_type = b.batch_type

        user_label = tr.started_by_name.split("@")[0] if tr.started_by_name else tr.started_by[:8]
        date_label = tr.started_at.strftime("%Y-%m-%d")
        time_label = tr.started_at.strftime("%H:%M")
        tr_label = f"{tr.layout_library} + {tr.ocr_library} ({date_label} {time_label})"

        # Batch job grouping
        batch_job_id = tr.batch_job_id or ""
        if batch_job_id:
            bj = batch_job_map.get(batch_job_id)
            if bj:
                bj_time = bj.started_at.strftime("%Y-%m-%d %H:%M")
                bj_label = f"Job {bj_time} ({bj.total_combinations} combos)"
            else:
                bj_label = f"Job {batch_job_id[:8]}"
            batch_jobs_set.add((batch_job_id, bj_label))

        # Prompt tracking
        ocr_prompt_id = getattr(tr, 'ocr_prompt_id', None) or ""
        ocr_prompt_name = getattr(tr, 'ocr_prompt_name', None) or "Default"
        if ocr_prompt_id:
            prompts_set.add((ocr_prompt_id, ocr_prompt_name))

        users_set.add(user_label)
        dates_set.add(date_label)
        batch_types_set.add(batch_type)
        for bid in tr.batch_ids:
            b = batch_map.get(bid)
            if b:
                batches_set.add((bid, f"{b.form_name} #{b.batch_number}"))
        test_runs_list.append({"id": tr.id, "label": tr_label})

        for result in results:
            documents_set.add(result.document_id)

            # Per-field data
            field_accuracies = {}
            for field in result.extracted_fields:
                fields_set.add(field.field_name)
                acc = field.match_score
                # Prefer verified/corrected accuracy
                if field.verification_status.value == "corrected" and field.corrected_value is not None:
                    acc = 1.0 if field.corrected_value.lower() == field.expected_value.lower() else field.match_score
                elif field.verification_status.value == "verified":
                    acc = field.match_score
                field_accuracies[field.field_name] = round(acc, 4)

            rows.append({
                "test_run_id": tr.id,
                "document_id": result.document_id,
                "batch_id": result.batch_id,
                "batch_job_id": batch_job_id,
                "batch_type": batch_type,
                "layout_library": tr.layout_library,
                "ocr_library": tr.ocr_library,
                "ocr_prompt_id": ocr_prompt_id,
                "ocr_prompt_name": ocr_prompt_name,
                "user": user_label,
                "date": date_label,
                "overall_accuracy": round(result.overall_accuracy, 4),
                "verified_accuracy": round(result.verified_accuracy, 4) if result.verified_accuracy is not None else None,
                "duration_s": duration_s,
                "total_documents": tr.total_documents,
                "field_accuracies": field_accuracies,
            })

    filters = {
        "users": sorted(users_set),
        "dates": sorted(dates_set, reverse=True),
        "batches": [{"id": bid, "label": label} for bid, label in sorted(batches_set, key=lambda x: x[1])],
        "batch_jobs": [{"id": bjid, "label": label} for bjid, label in sorted(batch_jobs_set, key=lambda x: x[1], reverse=True)],
        "batch_types": sorted(batch_types_set),
        "fields": sorted(fields_set),
        "test_runs": test_runs_list,
        "documents": sorted(documents_set),
        "prompts": [{"id": pid, "label": plabel} for pid, plabel in sorted(prompts_set, key=lambda x: x[1])],
    }

    return {"rows": rows, "filters": filters}


@router.get("/classification-matrix")
async def get_classification_matrix(
    current_user_id: str = Depends(get_current_user_id)
):
    """Return classification accuracy data grouped by classifier model."""
    firestore = FirestoreService()

    test_runs = await firestore.list_test_runs()
    completed_runs = [tr for tr in test_runs if tr.status.value == "completed"]

    if not completed_runs:
        return {"rows": [], "filters": {"users": [], "dates": [], "classifier_models": [], "prompts": []}}

    rows = []
    users_set = set()
    dates_set = set()
    models_set = set()
    cls_prompts_set = set()

    for tr in completed_runs:
        results = await firestore.get_results_by_test_run(tr.id)

        user_label = tr.started_by_name.split("@")[0] if tr.started_by_name else tr.started_by[:8]
        date_label = tr.started_at.strftime("%Y-%m-%d")

        for result in results:
            if not result.classification_results:
                continue

            classifier_model = result.classification_results.get("classifier_model", "unknown")
            cls_prompt_id = result.classification_results.get("prompt_id", "")
            cls_prompt_name = result.classification_results.get("prompt_name", "Default")
            models_set.add(classifier_model)
            if cls_prompt_id:
                cls_prompts_set.add((cls_prompt_id, cls_prompt_name))
            users_set.add(user_label)
            dates_set.add(date_label)

            rows.append({
                "test_run_id": tr.id,
                "document_id": result.document_id,
                "batch_id": result.batch_id,
                "classifier_model": classifier_model,
                "prompt_id": cls_prompt_id,
                "prompt_name": cls_prompt_name,
                "user": user_label,
                "date": date_label,
                "classification_verified_accuracy": (
                    round(result.classification_verified_accuracy, 4)
                    if result.classification_verified_accuracy is not None
                    else None
                ),
                "is_verified": result.classification_verified_by is not None,
            })

    filters = {
        "users": sorted(users_set),
        "dates": sorted(dates_set, reverse=True),
        "classifier_models": sorted(models_set),
        "prompts": [{"id": pid, "label": plabel} for pid, plabel in sorted(cls_prompts_set, key=lambda x: x[1])],
    }

    return {"rows": rows, "filters": filters}


@router.get("/aggregate")
async def get_aggregate_metrics(
    current_user_id: str = Depends(get_current_user_id)
):
    """Get aggregate metrics across all test runs."""
    firestore = FirestoreService()

    # Get all test runs
    test_runs = await firestore.list_test_runs()

    if not test_runs:
        return {
            "total_test_runs": 0,
            "total_documents_processed": 0,
            "average_accuracy": 0.0,
            "by_layout_library": {},
            "by_ocr_library": {}
        }

    # Collect all results
    all_results = []
    layout_results = {}
    ocr_results = {}

    for test_run in test_runs:
        if test_run.status.value != "completed":
            continue

        results = await firestore.get_results_by_test_run(test_run.id)
        all_results.extend(results)

        # Aggregate by layout library
        if test_run.layout_library not in layout_results:
            layout_results[test_run.layout_library] = {
                "count": 0,
                "total_accuracy": 0.0
            }
        layout_results[test_run.layout_library]["count"] += len(results)
        layout_results[test_run.layout_library]["total_accuracy"] += sum(
            [r.overall_accuracy for r in results]
        )

        # Aggregate by OCR library
        if test_run.ocr_library not in ocr_results:
            ocr_results[test_run.ocr_library] = {
                "count": 0,
                "total_accuracy": 0.0
            }
        ocr_results[test_run.ocr_library]["count"] += len(results)
        ocr_results[test_run.ocr_library]["total_accuracy"] += sum(
            [r.overall_accuracy for r in results]
        )

    # Calculate averages
    total_accuracy = sum([r.overall_accuracy for r in all_results])
    avg_accuracy = total_accuracy / len(all_results) if all_results else 0.0

    by_layout = {
        lib: round(data["total_accuracy"] / data["count"], 4)
        for lib, data in layout_results.items()
        if data["count"] > 0
    }

    by_ocr = {
        lib: round(data["total_accuracy"] / data["count"], 4)
        for lib, data in ocr_results.items()
        if data["count"] > 0
    }

    return {
        "total_test_runs": len([tr for tr in test_runs if tr.status.value == "completed"]),
        "total_documents_processed": len(all_results),
        "average_accuracy": round(avg_accuracy, 4),
        "by_layout_library": by_layout,
        "by_ocr_library": by_ocr
    }


@router.get("/by-field")
async def get_field_metrics(
    current_user_id: str = Depends(get_current_user_id)
):
    """Get per-field accuracy breakdown across all test runs."""
    firestore = FirestoreService()

    # Get all completed test runs
    test_runs = await firestore.list_test_runs()

    field_scores = {}
    field_counts = {}

    for test_run in test_runs:
        if test_run.status.value != "completed":
            continue

        results = await firestore.get_results_by_test_run(test_run.id)

        for result in results:
            for field in result.extracted_fields:
                if field.field_name not in field_scores:
                    field_scores[field.field_name] = 0.0
                    field_counts[field.field_name] = 0

                field_scores[field.field_name] += field.match_score
                field_counts[field.field_name] += 1

    # Calculate averages
    field_accuracies = {}
    for name in field_scores:
        if field_counts[name] > 0:
            field_accuracies[name] = {
                "average_accuracy": round(
                    field_scores[name] / field_counts[name], 4
                ),
                "sample_count": field_counts[name]
            }

    # Sort by accuracy (worst first for easy identification of problem fields)
    sorted_fields = dict(sorted(
        field_accuracies.items(),
        key=lambda x: x[1]["average_accuracy"]
    ))

    return {
        "fields": sorted_fields,
        "total_fields": len(sorted_fields)
    }


@router.get("/comparison")
async def get_comparison_metrics(
    test_run_ids: List[str] = Query(...),
    current_user_id: str = Depends(get_current_user_id)
):
    """Compare metrics across specific test runs."""
    firestore = FirestoreService()

    comparisons = []

    for test_run_id in test_run_ids:
        test_run = await firestore.get_test_run_by_id(test_run_id)
        if not test_run:
            continue

        results = await firestore.get_results_by_test_run(test_run_id)

        if not results:
            continue

        # Calculate metrics
        avg_accuracy = sum([r.overall_accuracy for r in results]) / len(results)

        # Per-field accuracy
        field_scores = {}
        field_counts = {}

        for result in results:
            for field in result.extracted_fields:
                if field.field_name not in field_scores:
                    field_scores[field.field_name] = 0.0
                    field_counts[field.field_name] = 0

                field_scores[field.field_name] += field.match_score
                field_counts[field.field_name] += 1

        field_accuracies = {
            name: round(field_scores[name] / field_counts[name], 4)
            for name in field_scores
            if field_counts[name] > 0
        }

        comparisons.append({
            "test_run_id": test_run_id,
            "layout_library": test_run.layout_library,
            "ocr_library": test_run.ocr_library,
            "document_count": len(results),
            "average_accuracy": round(avg_accuracy, 4),
            "field_accuracies": field_accuracies,
            "started_at": test_run.started_at.isoformat(),
            "completed_at": test_run.completed_at.isoformat() if test_run.completed_at else None,
        })

    return {"comparisons": comparisons}


@router.get("/export")
async def export_metrics(
    format: str = Query("csv", pattern="^(csv|json)$"),
    test_run_id: Optional[str] = Query(None),
    current_user_id: str = Depends(get_current_user_id)
):
    """Export metrics data as CSV or JSON."""
    firestore = FirestoreService()

    if test_run_id:
        test_runs = [await firestore.get_test_run_by_id(test_run_id)]
        test_runs = [tr for tr in test_runs if tr is not None]
    else:
        test_runs = await firestore.list_test_runs()
        test_runs = [tr for tr in test_runs if tr.status.value == "completed"]

    # Collect data for export
    export_data = []

    for test_run in test_runs:
        results = await firestore.get_results_by_test_run(test_run.id)

        for result in results:
            for field in result.extracted_fields:
                export_data.append({
                    "test_run_id": test_run.id,
                    "layout_library": test_run.layout_library,
                    "ocr_library": test_run.ocr_library,
                    "document_id": result.document_id,
                    "field_name": field.field_name,
                    "expected_value": field.expected_value,
                    "extracted_value": field.extracted_value,
                    "confidence": field.confidence,
                    "match_score": field.match_score,
                    "overall_accuracy": result.overall_accuracy
                })

    if format == "json":
        return {"data": export_data}

    # CSV export
    if not export_data:
        return StreamingResponse(
            io.StringIO("No data"),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=metrics.csv"}
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
    writer.writeheader()
    writer.writerows(export_data)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=metrics.csv"}
    )
