"""
Test execution routes.
"""
import logging
from typing import Optional, Dict, List
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks

from app.auth.dependencies import get_current_user_id
from app.models.test_run import (
    TestRunResponse,
    TestRunListResponse,
    RunTestsRequest,
    RunBatchJobRequest,
    BatchJobResponse,
    BatchJobListResponse,
    TestStatus,
)
from app.services.firestore import FirestoreService
from app.services.ocr_pipeline import OCRPipelineService
from app.processing.layout import list_layout_detectors
from app.processing.ocr import list_ocr_engines, VLM_ENGINES

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_test_background(
    test_run_id: str,
    batch_ids: list[str],
    layout_library: str,
    ocr_library: str,
    image_cache: Optional[Dict[str, bytes]] = None,
    ocr_prompt: Optional[str] = None,
    classifier_model: Optional[str] = None,
    classification_prompt: Optional[str] = None,
    field_types: Optional[List[str]] = None,
    judge_model: Optional[str] = None,
    judge_prompt: Optional[str] = None,
):
    """Background task to run OCR pipeline (and optionally classification + judge) on batches."""
    firestore = FirestoreService()
    # Use unified pipeline whenever a classifier model is set, even without field_types
    use_unified = bool(classifier_model)

    try:
        # Update status to running
        await firestore.update_test_run_status(
            test_run_id,
            TestStatus.RUNNING
        )

        total_processed = 0

        for batch_id in batch_ids:
            batch = await firestore.get_batch_by_id(batch_id)
            if not batch:
                continue

            if use_unified:
                from app.services.unified_pipeline import UnifiedPipelineService
                pipeline = UnifiedPipelineService()
                await pipeline.process_batch_unified(
                    batch=batch,
                    layout_library=layout_library,
                    ocr_library=ocr_library,
                    classifier_model=classifier_model,
                    field_types=field_types,
                    test_run_id=test_run_id,
                    ocr_prompt=ocr_prompt,
                    classification_prompt=classification_prompt,
                    progress_callback=lambda curr, total: firestore.update_test_run_status(
                        test_run_id,
                        TestStatus.RUNNING,
                        processed_documents=total_processed + curr
                    ),
                    image_cache=image_cache,
                    judge_model=judge_model,
                    judge_prompt=judge_prompt,
                )
            else:
                pipeline = OCRPipelineService()
                await pipeline.process_batch(
                    batch=batch,
                    layout_library=layout_library,
                    ocr_library=ocr_library,
                    test_run_id=test_run_id,
                    progress_callback=lambda curr, total: firestore.update_test_run_status(
                        test_run_id,
                        TestStatus.RUNNING,
                        processed_documents=total_processed + curr
                    ),
                    image_cache=image_cache,
                    ocr_prompt=ocr_prompt,
                )

            total_processed += len(batch.documents)

        # Update status to completed
        await firestore.update_test_run_status(
            test_run_id,
            TestStatus.COMPLETED,
            processed_documents=total_processed
        )

    except Exception as e:
        logger.error(f"Test run {test_run_id} failed: {e}", exc_info=True)
        # Update status to failed
        await firestore.update_test_run_status(
            test_run_id,
            TestStatus.FAILED,
            error_message=str(e)
        )


async def run_batch_job_background(
    job_id: str,
    batch_ids: list[str],
    layout_libraries: list[str],
    ocr_libraries: list[str],
    started_by: str,
    started_by_name: str,
    total_documents: int,
    ocr_prompt: Optional[str] = None,
    ocr_prompt_id: Optional[str] = None,
    ocr_prompt_name: Optional[str] = None,
    classifier_models: Optional[List[str]] = None,
    classification_prompt: Optional[str] = None,
    classification_prompt_id: Optional[str] = None,
    classification_prompt_name: Optional[str] = None,
    field_types: Optional[List[str]] = None,
    judge_model: Optional[str] = None,
    judge_prompt: Optional[str] = None,
    judge_prompt_id: Optional[str] = None,
    judge_prompt_name: Optional[str] = None,
):
    """Background task to run all layout+OCR combinations sequentially."""
    firestore = FirestoreService()

    try:
        await firestore.update_batch_job(job_id, status=TestStatus.RUNNING)

        # Shared image cache across all combinations
        image_cache: Dict[str, bytes] = {}

        vlm_engines = VLM_ENGINES
        completed = 0
        test_run_ids = []

        # Build combinations: VLM engines skip layout, traditional engines need layout
        # If classifier_models is provided, also iterate over those
        # Special sentinel "__same_as_ocr__" means pair each OCR with itself as classifier
        combinations = []
        same_as_ocr = classifier_models == ["__same_as_ocr__"]

        if same_as_ocr:
            # Import valid classifier model names
            from app.services.unified_pipeline import BEDROCK_CLASSIFIERS
            valid_classifiers = set(["claude"] + list(BEDROCK_CLASSIFIERS) + ["gpt5", "gpt5_mini"])

            for ocr_lib in ocr_libraries:
                if ocr_lib not in valid_classifiers:
                    continue  # Skip OCR engines that can't act as classifiers
                if ocr_lib in vlm_engines:
                    combinations.append(("none", ocr_lib, ocr_lib))
                else:
                    for layout_lib in layout_libraries:
                        combinations.append((layout_lib, ocr_lib, ocr_lib))
        else:
            cls_models = classifier_models or [None]
            for ocr_lib in ocr_libraries:
                for cls_model in cls_models:
                    if ocr_lib in vlm_engines:
                        combinations.append(("none", ocr_lib, cls_model))
                    else:
                        for layout_lib in layout_libraries:
                            combinations.append((layout_lib, ocr_lib, cls_model))

        for layout_lib, ocr_lib, cls_model in combinations:
            is_unified = bool(cls_model)
            # Create a test run for this combination
            test_run = await firestore.create_test_run(
                batch_ids=batch_ids,
                layout_library=layout_lib,
                ocr_library=ocr_lib,
                started_by=started_by,
                total_documents=total_documents,
                started_by_name=started_by_name,
                batch_job_id=job_id,
                ocr_prompt_id=ocr_prompt_id,
                ocr_prompt_name=ocr_prompt_name,
                classifier_model=cls_model,
                classification_prompt_id=classification_prompt_id,
                classification_prompt_name=classification_prompt_name,
                field_types=field_types,
                is_unified=is_unified,
                judge_model=judge_model,
                judge_prompt_id=judge_prompt_id,
                judge_prompt_name=judge_prompt_name,
            )
            test_run_ids.append(test_run.id)
            await firestore.update_batch_job(
                job_id, test_run_ids=test_run_ids
            )

            # Run this combination
            try:
                await run_test_background(
                    test_run_id=test_run.id,
                    batch_ids=batch_ids,
                    layout_library=layout_lib,
                    ocr_library=ocr_lib,
                    image_cache=image_cache,
                    ocr_prompt=ocr_prompt,
                    classifier_model=cls_model,
                    classification_prompt=classification_prompt,
                    field_types=field_types,
                    judge_model=judge_model,
                    judge_prompt=judge_prompt,
                )
            except Exception:
                # Individual combo failure doesn't stop the job
                pass

            completed += 1
            await firestore.update_batch_job(
                job_id, completed_combinations=completed
            )

        await firestore.update_batch_job(
            job_id,
            status=TestStatus.COMPLETED,
            completed_combinations=completed,
            test_run_ids=test_run_ids,
        )

    except Exception as e:
        await firestore.update_batch_job(
            job_id,
            status=TestStatus.FAILED,
            error_message=str(e),
        )


# ==================== Fixed-path routes (MUST come before /{test_run_id}) ====================

@router.post("/run", response_model=TestRunResponse)
async def run_tests(
    request: RunTestsRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id)
):
    """Start a test run on selected batches."""
    firestore = FirestoreService()

    total_documents = 0

    for batch_id in request.batch_ids:
        batch = await firestore.get_batch_by_id(batch_id)
        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch not found: {batch_id}"
            )
        total_documents += len(batch.documents)

    # VLM engines do full-page processing and don't need layout detection
    vlm_engines = VLM_ENGINES
    is_vlm_engine = request.ocr_library in vlm_engines

    # Classification-only mode: no OCR engine needed when classifier is set
    is_classification_only = request.ocr_library in ("none", "") and request.classifier_model

    # Validate layout library unless using a VLM engine or classification-only
    if not is_vlm_engine and not is_classification_only:
        available_layouts = list_layout_detectors()
        if request.layout_library not in available_layouts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid layout library. Available: {available_layouts}"
            )

    # Validate OCR library (skip for classification-only mode)
    if not is_classification_only:
        available_ocrs = list_ocr_engines()
        if request.ocr_library not in available_ocrs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OCR library. Available: {available_ocrs}"
            )

    if total_documents == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected batches contain no documents"
        )

    # Default layout_library for VLM engines or classification-only mode
    layout_library = request.layout_library
    if not layout_library and (is_vlm_engine or is_classification_only):
        layout_library = "none"

    # Look up user email
    user = await firestore.get_user_by_id(current_user_id)
    started_by_name = user.email if user else ""

    # Resolve OCR prompt if provided
    ocr_prompt_text = None
    ocr_prompt_name = None
    if request.ocr_prompt_id and request.ocr_prompt_id != "default":
        prompt_doc = await firestore.get_prompt(request.ocr_prompt_id)
        if prompt_doc:
            ocr_prompt_text = prompt_doc.prompt_text
            ocr_prompt_name = prompt_doc.name

    # Resolve classification prompt if provided
    classification_prompt_text = None
    classification_prompt_name = None
    if request.classification_prompt_id and request.classification_prompt_id != "default":
        cls_prompt_doc = await firestore.get_prompt(request.classification_prompt_id)
        if cls_prompt_doc:
            classification_prompt_text = cls_prompt_doc.prompt_text
            classification_prompt_name = cls_prompt_doc.name

    # Resolve judge prompt if provided
    judge_prompt_text = None
    judge_prompt_name = None
    if request.judge_prompt_id and request.judge_prompt_id != "default":
        judge_prompt_doc = await firestore.get_prompt(request.judge_prompt_id)
        if judge_prompt_doc:
            judge_prompt_text = judge_prompt_doc.prompt_text
            judge_prompt_name = judge_prompt_doc.name

    is_unified = bool(request.classifier_model)

    # Create test run record
    test_run = await firestore.create_test_run(
        batch_ids=request.batch_ids,
        layout_library=layout_library,
        ocr_library=request.ocr_library,
        started_by=current_user_id,
        total_documents=total_documents,
        started_by_name=started_by_name,
        ocr_prompt_id=request.ocr_prompt_id if request.ocr_prompt_id and request.ocr_prompt_id != "default" else None,
        ocr_prompt_name=ocr_prompt_name,
        classifier_model=request.classifier_model,
        classification_prompt_id=request.classification_prompt_id if request.classification_prompt_id and request.classification_prompt_id != "default" else None,
        classification_prompt_name=classification_prompt_name,
        field_types=request.field_types,
        is_unified=is_unified,
        judge_model=request.judge_model,
        judge_prompt_id=request.judge_prompt_id if request.judge_prompt_id and request.judge_prompt_id != "default" else None,
        judge_prompt_name=judge_prompt_name,
    )

    # Start background processing
    background_tasks.add_task(
        run_test_background,
        test_run.id,
        request.batch_ids,
        layout_library,
        request.ocr_library,
        None,  # image_cache
        ocr_prompt_text,
        request.classifier_model,
        classification_prompt_text,
        request.field_types,
        request.judge_model,
        judge_prompt_text,
    )

    return TestRunResponse(**test_run.model_dump())


@router.post("/batch-job", response_model=BatchJobResponse)
async def run_batch_job(
    request: RunBatchJobRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id)
):
    """Start a batch combination job (all layout x OCR combinations)."""
    firestore = FirestoreService()

    # Validate batches
    total_documents = 0
    for batch_id in request.batch_ids:
        batch = await firestore.get_batch_by_id(batch_id)
        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch not found: {batch_id}"
            )
        total_documents += len(batch.documents)

    if total_documents == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected batches contain no documents"
        )

    # Validate libraries
    available_layouts = list_layout_detectors()
    available_ocrs = list_ocr_engines()
    vlm_engines = VLM_ENGINES

    for lib in request.layout_libraries:
        if lib not in available_layouts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid layout library: {lib}. Available: {available_layouts}"
            )

    for lib in request.ocr_libraries:
        if lib not in available_ocrs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OCR library: {lib}. Available: {available_ocrs}"
            )

    # Calculate total combinations
    total_combos = 0
    same_as_ocr = request.classifier_models == ["__same_as_ocr__"]
    if same_as_ocr:
        from app.services.unified_pipeline import BEDROCK_CLASSIFIERS
        valid_classifiers = set(["claude"] + list(BEDROCK_CLASSIFIERS) + ["gpt5", "gpt5_mini"])
        for ocr_lib in request.ocr_libraries:
            if ocr_lib not in valid_classifiers:
                continue
            if ocr_lib in vlm_engines:
                total_combos += 1
            else:
                total_combos += len(request.layout_libraries)
    else:
        for ocr_lib in request.ocr_libraries:
            if ocr_lib in vlm_engines:
                total_combos += 1
            else:
                total_combos += len(request.layout_libraries)

    if total_combos == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid combinations to run"
        )

    # Look up user email
    user = await firestore.get_user_by_id(current_user_id)
    started_by_name = user.email if user else ""

    # Create batch job
    batch_job = await firestore.create_batch_job(
        batch_ids=request.batch_ids,
        layout_libraries=request.layout_libraries,
        ocr_libraries=request.ocr_libraries,
        started_by=current_user_id,
        total_combinations=total_combos,
        started_by_name=started_by_name,
    )

    # Resolve OCR prompt if provided
    ocr_prompt_text = None
    ocr_prompt_name = None
    if request.ocr_prompt_id and request.ocr_prompt_id != "default":
        prompt_doc = await firestore.get_prompt(request.ocr_prompt_id)
        if prompt_doc:
            ocr_prompt_text = prompt_doc.prompt_text
            ocr_prompt_name = prompt_doc.name

    # Resolve classification prompt if provided
    cls_prompt_text = None
    cls_prompt_name = None
    if request.classification_prompt_id and request.classification_prompt_id != "default":
        cls_prompt_doc = await firestore.get_prompt(request.classification_prompt_id)
        if cls_prompt_doc:
            cls_prompt_text = cls_prompt_doc.prompt_text
            cls_prompt_name = cls_prompt_doc.name

    # Resolve judge prompt if provided
    judge_prompt_text = None
    judge_prompt_name = None
    if request.judge_prompt_id and request.judge_prompt_id != "default":
        judge_prompt_doc = await firestore.get_prompt(request.judge_prompt_id)
        if judge_prompt_doc:
            judge_prompt_text = judge_prompt_doc.prompt_text
            judge_prompt_name = judge_prompt_doc.name

    # Start background processing
    background_tasks.add_task(
        run_batch_job_background,
        batch_job.id,
        request.batch_ids,
        request.layout_libraries,
        request.ocr_libraries,
        current_user_id,
        started_by_name,
        total_documents,
        ocr_prompt_text,
        request.ocr_prompt_id if request.ocr_prompt_id and request.ocr_prompt_id != "default" else None,
        ocr_prompt_name,
        request.classifier_models,
        cls_prompt_text,
        request.classification_prompt_id if request.classification_prompt_id and request.classification_prompt_id != "default" else None,
        cls_prompt_name,
        request.field_types,
        request.judge_model,
        judge_prompt_text,
        request.judge_prompt_id if request.judge_prompt_id and request.judge_prompt_id != "default" else None,
        judge_prompt_name,
    )

    return BatchJobResponse(**batch_job.model_dump())


@router.get("/batch-jobs", response_model=BatchJobListResponse)
async def list_batch_jobs(
    current_user_id: str = Depends(get_current_user_id)
):
    """List all batch combination jobs."""
    firestore = FirestoreService()
    jobs = await firestore.list_batch_jobs()
    return BatchJobListResponse(
        batch_jobs=[BatchJobResponse(**j.model_dump()) for j in jobs],
        total=len(jobs),
    )


@router.get("/batch-jobs/{job_id}", response_model=BatchJobResponse)
async def get_batch_job(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get batch job status."""
    firestore = FirestoreService()
    job = await firestore.get_batch_job_by_id(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch job not found"
        )
    return BatchJobResponse(**job.model_dump())


@router.post("/batch-jobs/{job_id}/cancel")
async def cancel_batch_job(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Cancel a stuck batch job and its child test runs."""
    firestore = FirestoreService()
    job = await firestore.get_batch_job_by_id(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch job not found"
        )

    if job.status not in [TestStatus.RUNNING, TestStatus.PENDING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch job is already {job.status.value}"
        )

    # Cancel all child test runs that are still running/pending
    cancelled_runs = 0
    for run_id in job.test_run_ids:
        run = await firestore.get_test_run_by_id(run_id)
        if run and run.status in [TestStatus.RUNNING, TestStatus.PENDING]:
            await firestore.update_test_run_status(
                run_id,
                TestStatus.FAILED,
                error_message="Cancelled — parent batch job was cancelled"
            )
            cancelled_runs += 1

    # Cancel the batch job itself
    await firestore.update_batch_job(
        job_id,
        status=TestStatus.FAILED,
        error_message="Cancelled by user"
    )

    return {
        "message": "Batch job cancelled",
        "id": job_id,
        "cancelled_test_runs": cancelled_runs
    }


@router.get("/options/libraries")
async def get_available_libraries(
    current_user_id: str = Depends(get_current_user_id)
):
    """Get available layout, OCR, classifier, and judge model libraries."""
    from app.processing.ocr import VLM_ENGINES
    from app.services.unified_pipeline import BEDROCK_CLASSIFIERS

    classifier_models = sorted(
        ["claude"] + list(BEDROCK_CLASSIFIERS) + ["gpt5", "gpt5_mini"]
    )

    return {
        "layout_libraries": list_layout_detectors(),
        "ocr_libraries": list_ocr_engines(),
        "vlm_engines": VLM_ENGINES,
        "classifier_models": classifier_models,
        "judge_models": classifier_models,  # Same models available as judges
    }


@router.get("", response_model=TestRunListResponse)
async def list_test_runs(current_user_id: str = Depends(get_current_user_id)):
    """List all test runs."""
    firestore = FirestoreService()
    test_runs = await firestore.list_test_runs()

    return TestRunListResponse(
        test_runs=[TestRunResponse(**tr.model_dump()) for tr in test_runs],
        total=len(test_runs)
    )


# ==================== Dynamic-path routes (MUST come after fixed routes) ====================

@router.get("/{test_run_id}", response_model=TestRunResponse)
async def get_test_run(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get test run details by ID."""
    firestore = FirestoreService()
    test_run = await firestore.get_test_run_by_id(test_run_id)

    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found"
        )

    return TestRunResponse(**test_run.model_dump())


@router.get("/{test_run_id}/status")
async def get_test_run_status(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get test run status (for polling during processing)."""
    firestore = FirestoreService()
    test_run = await firestore.get_test_run_by_id(test_run_id)

    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found"
        )

    return {
        "id": test_run.id,
        "status": test_run.status.value,
        "processed_documents": test_run.processed_documents,
        "total_documents": test_run.total_documents,
        "progress_percent": (
            (test_run.processed_documents / test_run.total_documents * 100)
            if test_run.total_documents > 0 else 0
        ),
        "error_message": test_run.error_message
    }


@router.post("/{test_run_id}/cancel")
async def cancel_test_run(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Cancel/reset a stuck test run."""
    firestore = FirestoreService()
    test_run = await firestore.get_test_run_by_id(test_run_id)

    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found"
        )

    if test_run.status not in [TestStatus.RUNNING, TestStatus.PENDING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Test run is already {test_run.status.value}"
        )

    await firestore.update_test_run_status(
        test_run_id,
        TestStatus.FAILED,
        error_message="Cancelled by user"
    )

    return {"message": "Test run cancelled", "id": test_run_id}
