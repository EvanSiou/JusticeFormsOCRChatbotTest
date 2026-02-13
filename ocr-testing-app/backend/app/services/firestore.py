"""
Firestore database service.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from google.cloud import firestore
from google.oauth2 import service_account

from app.config import get_settings
from app.models.user import UserInDB
from app.models.form import FormInDB, FieldMapping
from app.models.batch import BatchInDB, SyntheticDocument
from app.models.test_run import TestRunInDB, TestStatus, BatchJobInDB
from app.models.result import ResultInDB, ExtractedField

settings = get_settings()


class FirestoreService:
    """Service for Firestore database operations."""

    def __init__(self):
        """Initialize Firestore client."""
        if settings.google_application_credentials:
            credentials = service_account.Credentials.from_service_account_file(
                settings.google_application_credentials
            )
            self.db = firestore.Client(
                project=settings.gcp_project_id,
                credentials=credentials
            )
        else:
            # Use default credentials (for local development with gcloud auth)
            self.db = firestore.Client(project=settings.gcp_project_id)

    # ==================== User Operations ====================

    async def create_user(
        self,
        email: str,
        password_hash: str,
        created_by: Optional[str] = None
    ) -> UserInDB:
        """Create a new user."""
        user_id = str(uuid.uuid4())
        user_data = {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.utcnow(),
            "created_by": created_by,
        }

        self.db.collection("users").document(user_id).set(user_data)

        return UserInDB(**user_data)

    async def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        """Get user by ID."""
        doc = self.db.collection("users").document(user_id).get()
        if doc.exists:
            return UserInDB(**doc.to_dict())
        return None

    async def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        """Get user by email."""
        query = self.db.collection("users").where("email", "==", email).limit(1)
        docs = query.stream()

        for doc in docs:
            return UserInDB(**doc.to_dict())
        return None

    # ==================== Form Operations ====================

    async def create_form(
        self,
        name: str,
        storage_path: str,
        uploaded_by: str,
        form_type: str = "empty",
        uploaded_by_name: str = "",
        thumbnail_path: Optional[str] = None
    ) -> FormInDB:
        """Create a new form."""
        form_id = str(uuid.uuid4())
        form_data = {
            "id": form_id,
            "name": name,
            "form_type": form_type,
            "storage_path": storage_path,
            "uploaded_by": uploaded_by,
            "uploaded_by_name": uploaded_by_name,
            "uploaded_at": datetime.utcnow(),
            "field_mappings": [],
            "thumbnail_path": thumbnail_path,
        }

        self.db.collection("forms").document(form_id).set(form_data)

        return FormInDB(**form_data)

    async def get_form_by_id(self, form_id: str) -> Optional[FormInDB]:
        """Get form by ID."""
        doc = self.db.collection("forms").document(form_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["field_mappings"] = [
                FieldMapping(**fm) for fm in data.get("field_mappings", [])
            ]
            data.setdefault("form_type", "empty")
            data.setdefault("uploaded_by_name", "")
            data.setdefault("template_words", None)
            return FormInDB(**data)
        return None

    async def list_forms(self) -> List[FormInDB]:
        """List all forms."""
        docs = self.db.collection("forms").order_by("uploaded_at", direction=firestore.Query.DESCENDING).stream()
        forms = []
        for doc in docs:
            data = doc.to_dict()
            data["field_mappings"] = [
                FieldMapping(**fm) for fm in data.get("field_mappings", [])
            ]
            data.setdefault("form_type", "empty")
            data.setdefault("uploaded_by_name", "")
            data.setdefault("template_words", None)
            forms.append(FormInDB(**data))
        return forms

    async def update_form_field_mappings(
        self, form_id: str, field_mappings: List[FieldMapping]
    ) -> bool:
        """Update form field mappings."""
        doc_ref = self.db.collection("forms").document(form_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.update({
            "field_mappings": [fm.model_dump() for fm in field_mappings]
        })
        return True

    async def update_form_template_words(
        self, form_id: str, template_words: List[str]
    ) -> bool:
        """Update form template words for text cleanup."""
        doc_ref = self.db.collection("forms").document(form_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.update({
            "template_words": template_words
        })
        return True

    async def delete_form(self, form_id: str) -> bool:
        """Delete a form."""
        doc_ref = self.db.collection("forms").document(form_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.delete()
        return True

    # ==================== Batch Operations ====================

    async def create_batch(
        self,
        form_id: str,
        form_name: str,
        created_by: str,
        count: int,
        documents: List[SyntheticDocument],
        batch_type: str = "synthetic",
        created_by_name: str = "",
        skew_preset: Optional[str] = None,
        source_batch_ids: Optional[List[str]] = None,
    ) -> BatchInDB:
        """Create a new batch."""
        batch_id = str(uuid.uuid4())

        # Generate batch number (sequential)
        batch_count = len(list(self.db.collection("batches").stream()))
        batch_number = f"B{batch_count + 1:04d}"

        batch_data = {
            "id": batch_id,
            "batch_number": batch_number,
            "batch_type": batch_type,
            "form_id": form_id,
            "form_name": form_name,
            "created_by": created_by,
            "created_by_name": created_by_name,
            "created_at": datetime.utcnow(),
            "count": count,
            "skew_preset": skew_preset,
            "documents": [doc.model_dump() for doc in documents],
            "source_batch_ids": source_batch_ids,
        }

        self.db.collection("batches").document(batch_id).set(batch_data)

        return BatchInDB(**batch_data)

    async def get_batch_by_id(self, batch_id: str) -> Optional[BatchInDB]:
        """Get batch by ID."""
        doc = self.db.collection("batches").document(batch_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["documents"] = [
                SyntheticDocument(**d) for d in data.get("documents", [])
            ]
            data.setdefault("batch_type", "synthetic")
            data.setdefault("created_by_name", "")
            data.setdefault("skew_preset", None)
            data.setdefault("source_batch_ids", None)
            return BatchInDB(**data)
        return None

    async def list_batches(self) -> List[BatchInDB]:
        """List all batches."""
        docs = self.db.collection("batches").order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        batches = []
        for doc in docs:
            data = doc.to_dict()
            data["documents"] = [
                SyntheticDocument(**d) for d in data.get("documents", [])
            ]
            data.setdefault("batch_type", "synthetic")
            data.setdefault("created_by_name", "")
            data.setdefault("skew_preset", None)
            data.setdefault("source_batch_ids", None)
            batches.append(BatchInDB(**data))
        return batches

    async def delete_batch(self, batch_id: str) -> bool:
        """Delete a batch document."""
        doc_ref = self.db.collection("batches").document(batch_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        doc_ref.delete()
        return True

    async def append_documents_to_batch(
        self, batch_id: str, new_documents: List[SyntheticDocument]
    ) -> Optional[BatchInDB]:
        """Append documents to an existing batch."""
        doc_ref = self.db.collection("batches").document(batch_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        existing_docs = data.get("documents", [])
        existing_docs.extend([d.model_dump() for d in new_documents])
        doc_ref.update({
            "documents": existing_docs,
            "count": len(existing_docs),
        })
        return await self.get_batch_by_id(batch_id)

    async def remove_documents_from_batch(
        self, batch_id: str, document_ids: List[str]
    ) -> Optional[BatchInDB]:
        """Remove specific documents from a batch."""
        doc_ref = self.db.collection("batches").document(batch_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        remaining = [d for d in data.get("documents", []) if d["id"] not in document_ids]
        doc_ref.update({
            "documents": remaining,
            "count": len(remaining),
        })
        return await self.get_batch_by_id(batch_id)

    # ==================== Test Run Operations ====================

    async def create_test_run(
        self,
        batch_ids: List[str],
        layout_library: str,
        ocr_library: str,
        started_by: str,
        total_documents: int,
        started_by_name: str = "",
        batch_job_id: Optional[str] = None,
    ) -> TestRunInDB:
        """Create a new test run."""
        run_id = str(uuid.uuid4())
        run_data = {
            "id": run_id,
            "batch_ids": batch_ids,
            "layout_library": layout_library,
            "ocr_library": ocr_library,
            "started_by": started_by,
            "started_by_name": started_by_name,
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "status": TestStatus.PENDING.value,
            "error_message": None,
            "total_documents": total_documents,
            "processed_documents": 0,
            "batch_job_id": batch_job_id,
        }

        self.db.collection("test_runs").document(run_id).set(run_data)

        return TestRunInDB(**run_data)

    async def get_test_run_by_id(self, run_id: str) -> Optional[TestRunInDB]:
        """Get test run by ID."""
        doc = self.db.collection("test_runs").document(run_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["status"] = TestStatus(data["status"])
            data.setdefault("started_by_name", "")
            data.setdefault("batch_job_id", None)
            data.setdefault("last_heartbeat", None)
            return TestRunInDB(**data)
        return None

    async def update_test_run_status(
        self,
        run_id: str,
        status: TestStatus,
        processed_documents: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update test run status."""
        doc_ref = self.db.collection("test_runs").document(run_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        update_data: Dict[str, Any] = {
            "status": status.value,
            "last_heartbeat": datetime.utcnow(),
        }

        if processed_documents is not None:
            update_data["processed_documents"] = processed_documents

        if error_message is not None:
            update_data["error_message"] = error_message

        if status in [TestStatus.COMPLETED, TestStatus.FAILED]:
            update_data["completed_at"] = datetime.utcnow()

        doc_ref.update(update_data)
        return True

    # Stale threshold: if a running task hasn't sent a heartbeat in this long, mark it failed
    STALE_THRESHOLD = timedelta(minutes=30)

    async def list_test_runs(self) -> List[TestRunInDB]:
        """List all test runs. Auto-marks stale running tasks as failed."""
        docs = self.db.collection("test_runs").order_by("started_at", direction=firestore.Query.DESCENDING).stream()
        runs = []
        now = datetime.now(timezone.utc)
        for doc in docs:
            data = doc.to_dict()
            data["status"] = TestStatus(data["status"])
            data.setdefault("started_by_name", "")
            data.setdefault("batch_job_id", None)
            data.setdefault("last_heartbeat", None)

            # Auto-detect stale running tasks
            if data["status"] in [TestStatus.RUNNING, TestStatus.PENDING]:
                heartbeat = data.get("last_heartbeat")
                started = data.get("started_at")
                last_alive = heartbeat or started
                if last_alive:
                    # Ensure timezone-aware for comparison
                    if last_alive.tzinfo is None:
                        last_alive = last_alive.replace(tzinfo=timezone.utc)
                    if (now - last_alive) > self.STALE_THRESHOLD:
                        self.db.collection("test_runs").document(data["id"]).update({
                            "status": TestStatus.FAILED.value,
                            "error_message": "Timed out — Cloud Run instance was recycled",
                            "completed_at": now,
                        })
                        data["status"] = TestStatus.FAILED
                        data["error_message"] = "Timed out — Cloud Run instance was recycled"
                        data["completed_at"] = now

            runs.append(TestRunInDB(**data))
        return runs

    # ==================== Result Operations ====================

    async def create_result(
        self,
        test_run_id: str,
        document_id: str,
        batch_id: str,
        layout_results: Dict[str, Any],
        ocr_results: Dict[str, Any],
        extracted_fields: List[ExtractedField],
        overall_accuracy: float,
        classification_results: Optional[Dict[str, Any]] = None,
    ) -> ResultInDB:
        """Create a new result."""
        result_id = str(uuid.uuid4())
        result_data = {
            "id": result_id,
            "test_run_id": test_run_id,
            "document_id": document_id,
            "batch_id": batch_id,
            "layout_results": layout_results,
            "ocr_results": ocr_results,
            "extracted_fields": [ef.model_dump() for ef in extracted_fields],
            "overall_accuracy": overall_accuracy,
            "created_at": datetime.utcnow(),
        }
        if classification_results is not None:
            result_data["classification_results"] = classification_results

        self.db.collection("results").document(result_id).set(result_data)

        return ResultInDB(**result_data)

    async def get_results_by_test_run(self, test_run_id: str) -> List[ResultInDB]:
        """Get all results for a test run."""
        query = self.db.collection("results").where("test_run_id", "==", test_run_id)
        docs = query.stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["extracted_fields"] = [
                ExtractedField(**ef) for ef in data.get("extracted_fields", [])
            ]
            data.setdefault("classification_results", None)
            results.append(ResultInDB(**data))
        return results

    async def get_result_by_document(
        self, test_run_id: str, document_id: str
    ) -> Optional[ResultInDB]:
        """Get result for a specific document in a test run."""
        query = (
            self.db.collection("results")
            .where("test_run_id", "==", test_run_id)
            .where("document_id", "==", document_id)
            .limit(1)
        )
        docs = query.stream()
        for doc in docs:
            data = doc.to_dict()
            data["extracted_fields"] = [
                ExtractedField(**ef) for ef in data.get("extracted_fields", [])
            ]
            data.setdefault("classification_results", None)
            return ResultInDB(**data)
        return None

    async def update_result_verification(
        self,
        result_id: str,
        extracted_fields: List[ExtractedField],
        verified_accuracy: float,
        verified_by: str,
        verified_by_name: str = "",
    ) -> bool:
        """Update result with verification data."""
        doc_ref = self.db.collection("results").document(result_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.update({
            "extracted_fields": [ef.model_dump() for ef in extracted_fields],
            "verified_accuracy": verified_accuracy,
            "verified_by": verified_by,
            "verified_by_name": verified_by_name,
            "verified_at": datetime.utcnow(),
        })
        return True

    async def update_result_verification_handwritten(
        self,
        result_id: str,
        ocr_results: Dict[str, Any],
        verified_accuracy: float,
        verified_by: str,
        verified_by_name: str = "",
    ) -> bool:
        """Update result with handwritten verification data (text regions)."""
        doc_ref = self.db.collection("results").document(result_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.update({
            "ocr_results": ocr_results,
            "verified_accuracy": verified_accuracy,
            "verified_by": verified_by,
            "verified_by_name": verified_by_name,
            "verified_at": datetime.utcnow(),
        })
        return True

    async def get_result_by_id(self, result_id: str) -> Optional[ResultInDB]:
        """Get result by ID."""
        doc = self.db.collection("results").document(result_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["extracted_fields"] = [
                ExtractedField(**ef) for ef in data.get("extracted_fields", [])
            ]
            data.setdefault("classification_results", None)
            return ResultInDB(**data)
        return None

    async def update_result_cleaned_text(
        self, result_id: str, cleaned_text: str
    ) -> bool:
        """Update a result's ocr_results with cleaned text."""
        doc_ref = self.db.collection("results").document(result_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        data = doc.to_dict()
        ocr_results = data.get("ocr_results", {})
        ocr_results["cleaned_text"] = cleaned_text
        doc_ref.update({"ocr_results": ocr_results})
        return True

    async def update_result_classification(
        self, result_id: str, classification_results: Dict[str, Any]
    ) -> bool:
        """Update a result with classification data."""
        doc_ref = self.db.collection("results").document(result_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.update({"classification_results": classification_results})
        return True

    # ==================== Layout Cache Operations ====================

    @staticmethod
    def _layout_cache_key(storage_path: str, layout_library: str) -> str:
        """Generate a cache key from storage path and layout library."""
        raw = f"{storage_path}::{layout_library}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get_cached_layout(
        self, storage_path: str, layout_library: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached layout detection results."""
        cache_key = self._layout_cache_key(storage_path, layout_library)
        doc = self.db.collection("layout_cache").document(cache_key).get()
        if doc.exists:
            return doc.to_dict().get("layout_data")
        return None

    async def set_cached_layout(
        self, storage_path: str, layout_library: str, layout_data: Dict[str, Any]
    ) -> None:
        """Cache layout detection results."""
        cache_key = self._layout_cache_key(storage_path, layout_library)
        self.db.collection("layout_cache").document(cache_key).set({
            "storage_path": storage_path,
            "layout_library": layout_library,
            "layout_data": layout_data,
            "cached_at": datetime.utcnow(),
        })

    # ==================== Batch Job Operations ====================

    async def create_batch_job(
        self,
        batch_ids: List[str],
        layout_libraries: List[str],
        ocr_libraries: List[str],
        started_by: str,
        total_combinations: int,
        started_by_name: str = "",
    ) -> BatchJobInDB:
        """Create a new batch combination job."""
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "batch_ids": batch_ids,
            "layout_libraries": layout_libraries,
            "ocr_libraries": ocr_libraries,
            "started_by": started_by,
            "started_by_name": started_by_name,
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "status": TestStatus.PENDING.value,
            "test_run_ids": [],
            "total_combinations": total_combinations,
            "completed_combinations": 0,
            "error_message": None,
        }

        self.db.collection("batch_jobs").document(job_id).set(job_data)

        return BatchJobInDB(**job_data)

    async def get_batch_job_by_id(self, job_id: str) -> Optional[BatchJobInDB]:
        """Get batch job by ID."""
        doc = self.db.collection("batch_jobs").document(job_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["status"] = TestStatus(data["status"])
            data.setdefault("started_by_name", "")
            data.setdefault("last_heartbeat", None)
            return BatchJobInDB(**data)
        return None

    async def update_batch_job(
        self,
        job_id: str,
        status: Optional[TestStatus] = None,
        completed_combinations: Optional[int] = None,
        test_run_ids: Optional[List[str]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update batch job."""
        doc_ref = self.db.collection("batch_jobs").document(job_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        update_data: Dict[str, Any] = {
            "last_heartbeat": datetime.utcnow(),
        }

        if status is not None:
            update_data["status"] = status.value
            if status in [TestStatus.COMPLETED, TestStatus.FAILED]:
                update_data["completed_at"] = datetime.utcnow()

        if completed_combinations is not None:
            update_data["completed_combinations"] = completed_combinations

        if test_run_ids is not None:
            update_data["test_run_ids"] = test_run_ids

        if error_message is not None:
            update_data["error_message"] = error_message

        doc_ref.update(update_data)
        return True

    async def list_batch_jobs(self) -> List[BatchJobInDB]:
        """List all batch jobs. Auto-marks stale running jobs as failed."""
        docs = self.db.collection("batch_jobs").order_by(
            "started_at", direction=firestore.Query.DESCENDING
        ).stream()
        jobs = []
        now = datetime.now(timezone.utc)
        for doc in docs:
            data = doc.to_dict()
            data["status"] = TestStatus(data["status"])
            data.setdefault("started_by_name", "")
            data.setdefault("last_heartbeat", None)

            # Auto-detect stale running batch jobs
            if data["status"] in [TestStatus.RUNNING, TestStatus.PENDING]:
                heartbeat = data.get("last_heartbeat")
                started = data.get("started_at")
                last_alive = heartbeat or started
                if last_alive:
                    if last_alive.tzinfo is None:
                        last_alive = last_alive.replace(tzinfo=timezone.utc)
                    if (now - last_alive) > self.STALE_THRESHOLD:
                        self.db.collection("batch_jobs").document(data["id"]).update({
                            "status": TestStatus.FAILED.value,
                            "error_message": "Timed out — Cloud Run instance was recycled",
                            "completed_at": now,
                        })
                        data["status"] = TestStatus.FAILED
                        data["error_message"] = "Timed out — Cloud Run instance was recycled"
                        data["completed_at"] = now

            jobs.append(BatchJobInDB(**data))
        return jobs
