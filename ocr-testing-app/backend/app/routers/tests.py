"""
Test execution routes.
"""
import asyncio
from typing import Optional, Dict
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
from app.processing.ocr import list_ocr_engines

router = APIRouter()


async def run_test_background(
    test_run_id: str,
    batch_ids: list[str],
    layout_library: str,
    ocr_library: str,
    image_cache: Optional[Dict[str, bytes]] = None,
):
    """Background task to run OCR pipeline on batches."""
    firestore = FirestoreService()
    pipeline = OCRPipelineService()

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

            # Process batch
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
            )

            total_processed += len(batch.documents)

        # Update status to completed
        await firestore.update_test_run_status(
            test_run_id,
            TestStatus.COMPLETED,
            processed_documents=total_processed
        )

    except Exception as e:
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
):
    """Background task to run all layout+OCR combinations sequentially."""
    firestore = FirestoreService()

    try:
        await firestore.update_batch_job(job_id, status=TestStatus.RUNNING)

        # Shared image cache across all combinations
        image_cache: Dict[str, bytes] = {}

        vlm_engines = ['got_ocr', 'mineru']
        completed = 0
        test_run_ids = []

        # Build combinations: VLM engines skip layout, traditional engines need layout
        combinations = []
        for ocr_lib in ocr_libraries:
            if ocr_lib in vlm_engines:
                combinations.append(("none", ocr_lib))
            else:
                for layout_lib in layout_libraries:
                    combinations.append((layout_lib, ocr_lib))

        for layout_lib, ocr_lib in combinations:
            # Create a test run for this combination
            test_run = await firestore.create_test_run(
                batch_ids=batch_ids,
                layout_library=layout_lib,
                ocr_library=ocr_lib,
                started_by=started_by,
                total_documents=total_documents,
                started_by_name=started_by_name,
                batch_job_id=job_id,
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
    vlm_engines = ['got_ocr', 'mineru']
    is_vlm_engine = request.ocr_library in vlm_engines

    # Validate layout library unless using a VLM engine
    if not is_vlm_engine:
        available_layouts = list_layout_detectors()
        if request.layout_library not in available_layouts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid layout library. Available: {available_layouts}"
            )

    # Validate OCR library
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

    # Default layout_library for VLM engines
    layout_library = request.layout_library
    if not layout_library and is_vlm_engine:
        layout_library = "none"

    # Look up user email
    user = await firestore.get_user_by_id(current_user_id)
    started_by_name = user.email if user else ""

    # Create test run record
    test_run = await firestore.create_test_run(
        batch_ids=request.batch_ids,
        layout_library=layout_library,
        ocr_library=request.ocr_library,
        started_by=current_user_id,
        total_documents=total_documents,
        started_by_name=started_by_name,
    )

    # Start background processing
    background_tasks.add_task(
        run_test_background,
        test_run.id,
        request.batch_ids,
        layout_library,
        request.ocr_library
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
    vlm_engines = ['got_ocr', 'mineru']

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
    """Get available layout and OCR libraries."""
    return {
        "layout_libraries": list_layout_detectors(),
        "ocr_libraries": list_ocr_engines()
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
