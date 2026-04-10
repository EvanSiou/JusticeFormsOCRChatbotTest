"""
DynamoDB database service.
Replaces Firestore with AWS DynamoDB while keeping the same interface.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

import boto3
from boto3.dynamodb.conditions import Key, Attr

from app.config import get_settings
from app.models.user import UserInDB
from app.models.form import FormInDB, FieldMapping
from app.models.batch import BatchInDB, SyntheticDocument
from app.models.test_run import TestRunInDB, TestStatus, BatchJobInDB
from app.models.result import ResultInDB, ExtractedField
from app.models.prompt import PromptInDB, PromptType
from app.models.reference_data import ReferenceDataTemplate, ReferenceField

settings = get_settings()

_dynamodb_resource = None


def _get_resource():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        kwargs = {"region_name": settings.aws_default_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        _dynamodb_resource = boto3.resource("dynamodb", **kwargs)
    return _dynamodb_resource


def _now() -> str:
    return datetime.utcnow().isoformat()


def _parse_dt(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return val


def _to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(i) for i in obj]
    return obj


def _from_decimal(obj):
    if isinstance(obj, Decimal):
        if obj == int(obj):
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_decimal(i) for i in obj]
    return obj


def _clean_none(data: dict) -> dict:
    return {k: v for k, v in data.items() if v is not None}


class FirestoreService:
    """Service for DynamoDB database operations (same interface as Firestore version)."""

    def __init__(self):
        self._resource = _get_resource()
        self._prefix = settings.dynamodb_table_prefix

    def _table(self, name: str):
        return self._resource.Table(f"{self._prefix}-{name}")

    def _scan_sorted(self, table_name: str, sort_key: str = "created_at", reverse: bool = True) -> list:
        table = self._table(table_name)
        items = []
        response = table.scan()
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        items = [_from_decimal(item) for item in items]
        items.sort(key=lambda x: x.get(sort_key, ""), reverse=reverse)
        return items

    # ==================== User Operations ====================

    async def create_user(self, email: str, password_hash: str, created_by: Optional[str] = None) -> UserInDB:
        user_id = str(uuid.uuid4())
        user_data = {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "created_at": _now(),
            "created_by": created_by or "",
        }
        self._table("users").put_item(Item=_to_decimal(_clean_none(user_data)))
        user_data["created_by"] = created_by
        return UserInDB(**user_data)

    async def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        resp = self._table("users").get_item(Key={"id": user_id})
        item = resp.get("Item")
        if item:
            return UserInDB(**_from_decimal(item))
        return None

    async def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        resp = self._table("users").query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
            Limit=1,
        )
        items = resp.get("Items", [])
        if items:
            return UserInDB(**_from_decimal(items[0]))
        return None

    # ==================== Form Operations ====================

    async def create_form(self, name: str, storage_path: str, uploaded_by: str,
                          form_type: str = "empty", uploaded_by_name: str = "",
                          thumbnail_path: Optional[str] = None, page_count: int = 1) -> FormInDB:
        form_id = str(uuid.uuid4())
        form_data = {
            "id": form_id, "name": name, "form_type": form_type,
            "storage_path": storage_path, "uploaded_by": uploaded_by,
            "uploaded_by_name": uploaded_by_name, "uploaded_at": _now(),
            "field_mappings": [], "page_count": page_count,
        }
        if thumbnail_path:
            form_data["thumbnail_path"] = thumbnail_path
        self._table("forms").put_item(Item=_to_decimal(form_data))
        return FormInDB(**form_data)

    async def get_form_by_id(self, form_id: str) -> Optional[FormInDB]:
        resp = self._table("forms").get_item(Key={"id": form_id})
        item = resp.get("Item")
        if item:
            data = _from_decimal(item)
            data["field_mappings"] = [FieldMapping(**fm) for fm in data.get("field_mappings", [])]
            data.setdefault("form_type", "empty")
            data.setdefault("uploaded_by_name", "")
            data.setdefault("template_words", None)
            data.setdefault("page_count", 1)
            return FormInDB(**data)
        return None

    async def list_forms(self) -> List[FormInDB]:
        items = self._scan_sorted("forms", "uploaded_at")
        forms = []
        for data in items:
            data["field_mappings"] = [FieldMapping(**fm) for fm in data.get("field_mappings", [])]
            data.setdefault("form_type", "empty")
            data.setdefault("uploaded_by_name", "")
            data.setdefault("template_words", None)
            data.setdefault("page_count", 1)
            forms.append(FormInDB(**data))
        return forms

    async def update_form_field_mappings(self, form_id: str, field_mappings: List[FieldMapping]) -> bool:
        table = self._table("forms")
        resp = table.get_item(Key={"id": form_id})
        if "Item" not in resp:
            return False
        table.update_item(
            Key={"id": form_id},
            UpdateExpression="SET field_mappings = :fm",
            ExpressionAttributeValues={":fm": _to_decimal([fm.model_dump() for fm in field_mappings])},
        )
        return True

    async def update_form_template_words(self, form_id: str, template_words: List[str]) -> bool:
        table = self._table("forms")
        resp = table.get_item(Key={"id": form_id})
        if "Item" not in resp:
            return False
        table.update_item(
            Key={"id": form_id},
            UpdateExpression="SET template_words = :tw",
            ExpressionAttributeValues={":tw": template_words},
        )
        return True

    async def delete_form(self, form_id: str) -> bool:
        table = self._table("forms")
        resp = table.get_item(Key={"id": form_id})
        if "Item" not in resp:
            return False
        table.delete_item(Key={"id": form_id})
        return True

    # ==================== Batch Operations ====================

    async def create_batch(self, form_id: str, form_name: str, created_by: str, count: int,
                           documents: List[SyntheticDocument], batch_type: str = "synthetic",
                           created_by_name: str = "", skew_preset: Optional[str] = None,
                           source_batch_ids: Optional[List[str]] = None, page_count: int = 1) -> BatchInDB:
        batch_id = str(uuid.uuid4())
        existing = self._scan_sorted("batches", "created_at", reverse=False)
        batch_number = f"B{len(existing) + 1:04d}"
        batch_data = {
            "id": batch_id, "batch_number": batch_number, "batch_type": batch_type,
            "form_id": form_id, "form_name": form_name, "created_by": created_by,
            "created_by_name": created_by_name, "created_at": _now(), "count": count,
            "documents": [doc.model_dump() for doc in documents], "page_count": page_count,
        }
        if skew_preset:
            batch_data["skew_preset"] = skew_preset
        if source_batch_ids:
            batch_data["source_batch_ids"] = source_batch_ids
        self._table("batches").put_item(Item=_to_decimal(batch_data))
        return BatchInDB(**batch_data)

    async def get_batch_by_id(self, batch_id: str) -> Optional[BatchInDB]:
        resp = self._table("batches").get_item(Key={"id": batch_id})
        item = resp.get("Item")
        if item:
            data = _from_decimal(item)
            data["documents"] = [SyntheticDocument(**d) for d in data.get("documents", [])]
            data.setdefault("batch_type", "synthetic")
            data.setdefault("created_by_name", "")
            data.setdefault("skew_preset", None)
            data.setdefault("source_batch_ids", None)
            data.setdefault("page_count", 1)
            data.setdefault("reference_template_id", None)
            return BatchInDB(**data)
        return None

    async def list_batches(self) -> List[BatchInDB]:
        items = self._scan_sorted("batches", "created_at")
        batches = []
        for data in items:
            data["documents"] = [SyntheticDocument(**d) for d in data.get("documents", [])]
            data.setdefault("batch_type", "synthetic")
            data.setdefault("created_by_name", "")
            data.setdefault("skew_preset", None)
            data.setdefault("source_batch_ids", None)
            data.setdefault("page_count", 1)
            data.setdefault("reference_template_id", None)
            batches.append(BatchInDB(**data))
        return batches

    async def delete_batch(self, batch_id: str) -> bool:
        table = self._table("batches")
        resp = table.get_item(Key={"id": batch_id})
        if "Item" not in resp:
            return False
        table.delete_item(Key={"id": batch_id})
        return True

    async def append_documents_to_batch(self, batch_id: str, new_documents: List[SyntheticDocument]) -> Optional[BatchInDB]:
        table = self._table("batches")
        resp = table.get_item(Key={"id": batch_id})
        if "Item" not in resp:
            return None
        data = _from_decimal(resp["Item"])
        existing_docs = data.get("documents", [])
        existing_docs.extend([d.model_dump() for d in new_documents])
        table.update_item(
            Key={"id": batch_id},
            UpdateExpression="SET documents = :docs, #cnt = :cnt",
            ExpressionAttributeNames={"#cnt": "count"},
            ExpressionAttributeValues={":docs": _to_decimal(existing_docs), ":cnt": len(existing_docs)},
        )
        return await self.get_batch_by_id(batch_id)

    async def remove_documents_from_batch(self, batch_id: str, document_ids: List[str]) -> Optional[BatchInDB]:
        table = self._table("batches")
        resp = table.get_item(Key={"id": batch_id})
        if "Item" not in resp:
            return None
        data = _from_decimal(resp["Item"])
        remaining = [d for d in data.get("documents", []) if d["id"] not in document_ids]
        table.update_item(
            Key={"id": batch_id},
            UpdateExpression="SET documents = :docs, #cnt = :cnt",
            ExpressionAttributeNames={"#cnt": "count"},
            ExpressionAttributeValues={":docs": _to_decimal(remaining), ":cnt": len(remaining)},
        )
        return await self.get_batch_by_id(batch_id)

    # ==================== Test Run Operations ====================

    async def create_test_run(self, batch_ids: List[str], layout_library: str, ocr_library: str,
                              started_by: str, total_documents: int, started_by_name: str = "",
                              batch_job_id: Optional[str] = None, ocr_prompt_id: Optional[str] = None,
                              ocr_prompt_name: Optional[str] = None, classifier_model: Optional[str] = None,
                              classification_prompt_id: Optional[str] = None, classification_prompt_name: Optional[str] = None,
                              field_types: Optional[List[str]] = None, is_unified: bool = False,
                              judge_model: Optional[str] = None, judge_prompt_id: Optional[str] = None,
                              judge_prompt_name: Optional[str] = None) -> TestRunInDB:
        run_id = str(uuid.uuid4())
        run_data = {
            "id": run_id, "batch_ids": batch_ids, "layout_library": layout_library,
            "ocr_library": ocr_library, "started_by": started_by, "started_by_name": started_by_name,
            "started_at": _now(), "status": TestStatus.PENDING.value,
            "total_documents": total_documents, "processed_documents": 0, "is_unified": is_unified,
        }
        for key, val in {"batch_job_id": batch_job_id, "ocr_prompt_id": ocr_prompt_id,
                         "ocr_prompt_name": ocr_prompt_name, "classifier_model": classifier_model,
                         "classification_prompt_id": classification_prompt_id,
                         "classification_prompt_name": classification_prompt_name,
                         "field_types": field_types, "judge_model": judge_model,
                         "judge_prompt_id": judge_prompt_id, "judge_prompt_name": judge_prompt_name}.items():
            if val is not None:
                run_data[key] = val
        self._table("test-runs").put_item(Item=_to_decimal(run_data))
        run_data.setdefault("completed_at", None)
        run_data.setdefault("error_message", None)
        for k in ["batch_job_id", "ocr_prompt_id", "ocr_prompt_name", "classifier_model",
                   "classification_prompt_id", "classification_prompt_name", "field_types",
                   "judge_model", "judge_prompt_id", "judge_prompt_name"]:
            run_data.setdefault(k, None)
        return TestRunInDB(**run_data)

    async def get_test_run_by_id(self, run_id: str) -> Optional[TestRunInDB]:
        resp = self._table("test-runs").get_item(Key={"id": run_id})
        item = resp.get("Item")
        if item:
            data = _from_decimal(item)
            data["status"] = TestStatus(data["status"])
            for k in ["started_by_name", "batch_job_id", "last_heartbeat", "completed_at",
                       "error_message", "ocr_prompt_id", "ocr_prompt_name", "classifier_model",
                       "classification_prompt_id", "classification_prompt_name", "field_types",
                       "judge_model", "judge_prompt_id", "judge_prompt_name"]:
                data.setdefault(k, None)
            data.setdefault("started_by_name", "")
            data.setdefault("is_unified", False)
            return TestRunInDB(**data)
        return None

    async def update_test_run_status(self, run_id: str, status: TestStatus,
                                     processed_documents: Optional[int] = None,
                                     error_message: Optional[str] = None) -> bool:
        table = self._table("test-runs")
        resp = table.get_item(Key={"id": run_id})
        if "Item" not in resp:
            return False
        expr_parts = ["#st = :st", "last_heartbeat = :hb"]
        names = {"#st": "status"}
        values: Dict[str, Any] = {":st": status.value, ":hb": _now()}
        if processed_documents is not None:
            expr_parts.append("processed_documents = :pd")
            values[":pd"] = processed_documents
        if error_message is not None:
            expr_parts.append("error_message = :em")
            values[":em"] = error_message
        if status in [TestStatus.COMPLETED, TestStatus.FAILED]:
            expr_parts.append("completed_at = :ca")
            values[":ca"] = _now()
        table.update_item(
            Key={"id": run_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=_to_decimal(values),
        )
        return True

    STALE_THRESHOLD = timedelta(minutes=30)

    async def list_test_runs(self) -> List[TestRunInDB]:
        items = self._scan_sorted("test-runs", "started_at")
        runs = []
        now = datetime.now(timezone.utc)
        for data in items:
            data["status"] = TestStatus(data["status"])
            for k in ["started_by_name", "batch_job_id", "last_heartbeat", "completed_at",
                       "error_message", "ocr_prompt_id", "ocr_prompt_name", "classifier_model",
                       "classification_prompt_id", "classification_prompt_name", "field_types",
                       "judge_model", "judge_prompt_id", "judge_prompt_name"]:
                data.setdefault(k, None)
            data.setdefault("started_by_name", "")
            data.setdefault("is_unified", False)
            if data["status"] in [TestStatus.RUNNING, TestStatus.PENDING]:
                last_alive = _parse_dt(data.get("last_heartbeat")) or _parse_dt(data.get("started_at"))
                if last_alive:
                    if last_alive.tzinfo is None:
                        last_alive = last_alive.replace(tzinfo=timezone.utc)
                    if (now - last_alive) > self.STALE_THRESHOLD:
                        now_str = _now()
                        self._table("test-runs").update_item(
                            Key={"id": data["id"]},
                            UpdateExpression="SET #st = :st, error_message = :em, completed_at = :ca",
                            ExpressionAttributeNames={"#st": "status"},
                            ExpressionAttributeValues={":st": TestStatus.FAILED.value,
                                                       ":em": "Timed out — compute instance was recycled", ":ca": now_str},
                        )
                        data["status"] = TestStatus.FAILED
                        data["error_message"] = "Timed out — compute instance was recycled"
                        data["completed_at"] = now_str
            runs.append(TestRunInDB(**data))
        return runs

    # ==================== Result Operations ====================

    async def create_result(self, test_run_id: str, document_id: str, batch_id: str,
                            layout_results: Dict[str, Any], ocr_results: Dict[str, Any],
                            extracted_fields: List[ExtractedField], overall_accuracy: float,
                            classification_results: Optional[Dict[str, Any]] = None,
                            ocr_accuracy: Optional[float] = None, classification_accuracy: Optional[float] = None,
                            judge_results: Optional[Dict[str, Any]] = None, judge_model: Optional[str] = None,
                            judge_overall_score: Optional[float] = None) -> ResultInDB:
        result_id = str(uuid.uuid4())
        result_data = {
            "id": result_id, "test_run_id": test_run_id, "document_id": document_id,
            "batch_id": batch_id, "layout_results": layout_results, "ocr_results": ocr_results,
            "extracted_fields": [ef.model_dump() for ef in extracted_fields],
            "overall_accuracy": overall_accuracy, "created_at": _now(),
        }
        for key, val in {"classification_results": classification_results, "ocr_accuracy": ocr_accuracy,
                         "classification_accuracy": classification_accuracy, "judge_results": judge_results,
                         "judge_model": judge_model, "judge_overall_score": judge_overall_score}.items():
            if val is not None:
                result_data[key] = val
        self._table("results").put_item(Item=_to_decimal(result_data))
        for k in ["classification_results", "ocr_accuracy", "classification_accuracy",
                   "judge_results", "judge_model", "judge_overall_score"]:
            result_data.setdefault(k, None)
        return ResultInDB(**result_data)

    def _hydrate_result(self, data: dict) -> ResultInDB:
        data["extracted_fields"] = [ExtractedField(**ef) for ef in data.get("extracted_fields", [])]
        for k in ["classification_results", "classification_verified_accuracy", "classification_verified_by",
                   "classification_verified_by_name", "classification_verified_at", "ocr_accuracy",
                   "classification_accuracy", "judge_results", "judge_model", "judge_overall_score"]:
            data.setdefault(k, None)
        return ResultInDB(**data)

    async def get_results_by_test_run(self, test_run_id: str) -> List[ResultInDB]:
        table = self._table("results")
        resp = table.query(IndexName="test_run_id-index", KeyConditionExpression=Key("test_run_id").eq(test_run_id))
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.query(IndexName="test_run_id-index", KeyConditionExpression=Key("test_run_id").eq(test_run_id),
                               ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        return [self._hydrate_result(_from_decimal(item)) for item in items]

    async def get_result_by_document(self, test_run_id: str, document_id: str) -> Optional[ResultInDB]:
        table = self._table("results")
        resp = table.query(IndexName="test_run_id-index", KeyConditionExpression=Key("test_run_id").eq(test_run_id),
                           FilterExpression=Attr("document_id").eq(document_id), Limit=1)
        items = resp.get("Items", [])
        if items:
            return self._hydrate_result(_from_decimal(items[0]))
        return None

    async def update_result_verification(self, result_id: str, extracted_fields: List[ExtractedField],
                                         verified_accuracy: float, verified_by: str, verified_by_name: str = "") -> bool:
        table = self._table("results")
        resp = table.get_item(Key={"id": result_id})
        if "Item" not in resp:
            return False
        table.update_item(
            Key={"id": result_id},
            UpdateExpression="SET extracted_fields = :ef, verified_accuracy = :va, verified_by = :vb, verified_by_name = :vn, verified_at = :vt",
            ExpressionAttributeValues=_to_decimal({
                ":ef": [ef.model_dump() for ef in extracted_fields], ":va": verified_accuracy,
                ":vb": verified_by, ":vn": verified_by_name, ":vt": _now(),
            }),
        )
        return True

    async def update_result_verification_handwritten(self, result_id: str, ocr_results: Dict[str, Any],
                                                     verified_accuracy: float, verified_by: str,
                                                     verified_by_name: str = "") -> bool:
        table = self._table("results")
        resp = table.get_item(Key={"id": result_id})
        if "Item" not in resp:
            return False
        table.update_item(
            Key={"id": result_id},
            UpdateExpression="SET ocr_results = :or_val, verified_accuracy = :va, verified_by = :vb, verified_by_name = :vn, verified_at = :vt",
            ExpressionAttributeValues=_to_decimal({
                ":or_val": ocr_results, ":va": verified_accuracy,
                ":vb": verified_by, ":vn": verified_by_name, ":vt": _now(),
            }),
        )
        return True

    async def get_result_by_id(self, result_id: str) -> Optional[ResultInDB]:
        resp = self._table("results").get_item(Key={"id": result_id})
        item = resp.get("Item")
        if item:
            return self._hydrate_result(_from_decimal(item))
        return None

    async def update_result_cleaned_text(self, result_id: str, cleaned_text: str) -> bool:
        table = self._table("results")
        resp = table.get_item(Key={"id": result_id})
        if "Item" not in resp:
            return False
        data = _from_decimal(resp["Item"])
        ocr_results = data.get("ocr_results", {})
        ocr_results["cleaned_text"] = cleaned_text
        table.update_item(Key={"id": result_id}, UpdateExpression="SET ocr_results = :or_val",
                          ExpressionAttributeValues=_to_decimal({":or_val": ocr_results}))
        return True

    async def update_result_classification(self, result_id: str, classification_results: Dict[str, Any]) -> bool:
        table = self._table("results")
        resp = table.get_item(Key={"id": result_id})
        if "Item" not in resp:
            return False
        table.update_item(Key={"id": result_id}, UpdateExpression="SET classification_results = :cr",
                          ExpressionAttributeValues=_to_decimal({":cr": classification_results}))
        return True

    async def update_result_classification_verification(self, result_id: str, classification_results: Dict[str, Any],
                                                        verified_accuracy: float, verified_by: str,
                                                        verified_by_name: str = "") -> bool:
        table = self._table("results")
        resp = table.get_item(Key={"id": result_id})
        if "Item" not in resp:
            return False
        table.update_item(
            Key={"id": result_id},
            UpdateExpression="SET classification_results = :cr, classification_verified_accuracy = :va, classification_verified_by = :vb, classification_verified_by_name = :vn, classification_verified_at = :vt",
            ExpressionAttributeValues=_to_decimal({
                ":cr": classification_results, ":va": verified_accuracy,
                ":vb": verified_by, ":vn": verified_by_name, ":vt": _now(),
            }),
        )
        return True

    # ==================== Layout Cache Operations ====================

    @staticmethod
    def _layout_cache_key(storage_path: str, layout_library: str) -> str:
        raw = f"{storage_path}::{layout_library}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get_cached_layout(self, storage_path: str, layout_library: str) -> Optional[Dict[str, Any]]:
        cache_key = self._layout_cache_key(storage_path, layout_library)
        resp = self._table("layout-cache").get_item(Key={"cache_key": cache_key})
        item = resp.get("Item")
        if item:
            return _from_decimal(item).get("layout_data")
        return None

    async def set_cached_layout(self, storage_path: str, layout_library: str, layout_data: Dict[str, Any]) -> None:
        cache_key = self._layout_cache_key(storage_path, layout_library)
        self._table("layout-cache").put_item(Item=_to_decimal({
            "cache_key": cache_key, "storage_path": storage_path,
            "layout_library": layout_library, "layout_data": layout_data, "cached_at": _now(),
        }))

    # ==================== Batch Job Operations ====================

    async def create_batch_job(self, batch_ids: List[str], layout_libraries: List[str],
                               ocr_libraries: List[str], started_by: str, total_combinations: int,
                               started_by_name: str = "") -> BatchJobInDB:
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id, "batch_ids": batch_ids, "layout_libraries": layout_libraries,
            "ocr_libraries": ocr_libraries, "started_by": started_by, "started_by_name": started_by_name,
            "started_at": _now(), "status": TestStatus.PENDING.value,
            "test_run_ids": [], "total_combinations": total_combinations, "completed_combinations": 0,
        }
        self._table("batch-jobs").put_item(Item=_to_decimal(job_data))
        job_data["completed_at"] = None
        job_data["error_message"] = None
        return BatchJobInDB(**job_data)

    async def get_batch_job_by_id(self, job_id: str) -> Optional[BatchJobInDB]:
        resp = self._table("batch-jobs").get_item(Key={"id": job_id})
        item = resp.get("Item")
        if item:
            data = _from_decimal(item)
            data["status"] = TestStatus(data["status"])
            data.setdefault("started_by_name", "")
            data.setdefault("last_heartbeat", None)
            data.setdefault("completed_at", None)
            data.setdefault("error_message", None)
            return BatchJobInDB(**data)
        return None

    async def update_batch_job(self, job_id: str, status: Optional[TestStatus] = None,
                               completed_combinations: Optional[int] = None,
                               test_run_ids: Optional[List[str]] = None,
                               error_message: Optional[str] = None) -> bool:
        table = self._table("batch-jobs")
        resp = table.get_item(Key={"id": job_id})
        if "Item" not in resp:
            return False
        expr_parts = ["last_heartbeat = :hb"]
        names = {}
        values: Dict[str, Any] = {":hb": _now()}
        if status is not None:
            expr_parts.append("#st = :st")
            names["#st"] = "status"
            values[":st"] = status.value
            if status in [TestStatus.COMPLETED, TestStatus.FAILED]:
                expr_parts.append("completed_at = :ca")
                values[":ca"] = _now()
        if completed_combinations is not None:
            expr_parts.append("completed_combinations = :cc")
            values[":cc"] = completed_combinations
        if test_run_ids is not None:
            expr_parts.append("test_run_ids = :tri")
            values[":tri"] = test_run_ids
        if error_message is not None:
            expr_parts.append("error_message = :em")
            values[":em"] = error_message
        update_kwargs = {
            "Key": {"id": job_id},
            "UpdateExpression": "SET " + ", ".join(expr_parts),
            "ExpressionAttributeValues": _to_decimal(values),
        }
        if names:
            update_kwargs["ExpressionAttributeNames"] = names
        table.update_item(**update_kwargs)
        return True

    async def list_batch_jobs(self) -> List[BatchJobInDB]:
        items = self._scan_sorted("batch-jobs", "started_at")
        jobs = []
        now = datetime.now(timezone.utc)
        for data in items:
            data["status"] = TestStatus(data["status"])
            data.setdefault("started_by_name", "")
            data.setdefault("last_heartbeat", None)
            data.setdefault("completed_at", None)
            data.setdefault("error_message", None)
            if data["status"] in [TestStatus.RUNNING, TestStatus.PENDING]:
                last_alive = _parse_dt(data.get("last_heartbeat")) or _parse_dt(data.get("started_at"))
                if last_alive:
                    if last_alive.tzinfo is None:
                        last_alive = last_alive.replace(tzinfo=timezone.utc)
                    if (now - last_alive) > self.STALE_THRESHOLD:
                        now_str = _now()
                        self._table("batch-jobs").update_item(
                            Key={"id": data["id"]},
                            UpdateExpression="SET #st = :st, error_message = :em, completed_at = :ca",
                            ExpressionAttributeNames={"#st": "status"},
                            ExpressionAttributeValues={":st": TestStatus.FAILED.value,
                                                       ":em": "Timed out — compute instance was recycled", ":ca": now_str},
                        )
                        data["status"] = TestStatus.FAILED
                        data["error_message"] = "Timed out — compute instance was recycled"
                        data["completed_at"] = now_str
            jobs.append(BatchJobInDB(**data))
        return jobs

    # ==================== Prompt Operations ====================

    async def create_prompt(self, name: str, prompt_type: str, prompt_text: str,
                            created_by: str, created_by_name: str = "") -> PromptInDB:
        prompt_id = str(uuid.uuid4())
        now = _now()
        data = {
            "id": prompt_id, "name": name, "prompt_type": prompt_type,
            "prompt_text": prompt_text, "is_default": False,
            "created_by": created_by, "created_by_name": created_by_name, "created_at": now,
        }
        self._table("prompts").put_item(Item=_to_decimal(data))
        data["updated_at"] = None
        return PromptInDB(**data)

    async def get_prompt(self, prompt_id: str) -> Optional[PromptInDB]:
        resp = self._table("prompts").get_item(Key={"id": prompt_id})
        item = resp.get("Item")
        if item:
            data = _from_decimal(item)
            data.setdefault("updated_at", None)
            return PromptInDB(**data)
        return None

    async def list_prompts(self, prompt_type: Optional[str] = None) -> List[PromptInDB]:
        items = self._scan_sorted("prompts", "created_at")
        if prompt_type:
            items = [i for i in items if i.get("prompt_type") == prompt_type]
        return [PromptInDB(**{**data, "updated_at": data.get("updated_at")}) for data in items]

    async def update_prompt(self, prompt_id: str, name: Optional[str] = None, prompt_text: Optional[str] = None) -> bool:
        table = self._table("prompts")
        resp = table.get_item(Key={"id": prompt_id})
        if "Item" not in resp:
            return False
        expr_parts = ["updated_at = :ua"]
        values: Dict[str, Any] = {":ua": _now()}
        names = {}
        if name is not None:
            expr_parts.append("#n = :n")
            names["#n"] = "name"
            values[":n"] = name
        if prompt_text is not None:
            expr_parts.append("prompt_text = :pt")
            values[":pt"] = prompt_text
        update_kwargs = {"Key": {"id": prompt_id}, "UpdateExpression": "SET " + ", ".join(expr_parts),
                         "ExpressionAttributeValues": _to_decimal(values)}
        if names:
            update_kwargs["ExpressionAttributeNames"] = names
        table.update_item(**update_kwargs)
        return True

    async def delete_prompt(self, prompt_id: str) -> bool:
        table = self._table("prompts")
        resp = table.get_item(Key={"id": prompt_id})
        if "Item" not in resp:
            return False
        table.delete_item(Key={"id": prompt_id})
        return True

    # ==================== Reference Data Template Operations ====================

    async def create_reference_template(self, name: str, fields: List[ReferenceField], created_by: str,
                                        created_by_name: str = "", form_type_description: str = "") -> ReferenceDataTemplate:
        template_id = str(uuid.uuid4())
        now = _now()
        data = {
            "id": template_id, "name": name, "form_type_description": form_type_description,
            "fields": [f.model_dump() for f in fields], "created_by": created_by,
            "created_by_name": created_by_name, "created_at": now,
        }
        self._table("reference-templates").put_item(Item=_to_decimal(data))
        data["updated_at"] = None
        return ReferenceDataTemplate(**data)

    async def get_reference_template(self, template_id: str) -> Optional[ReferenceDataTemplate]:
        resp = self._table("reference-templates").get_item(Key={"id": template_id})
        item = resp.get("Item")
        if item:
            data = _from_decimal(item)
            data["fields"] = [ReferenceField(**f) for f in data.get("fields", [])]
            data.setdefault("form_type_description", "")
            data.setdefault("created_by_name", "")
            data.setdefault("updated_at", None)
            return ReferenceDataTemplate(**data)
        return None

    async def list_reference_templates(self) -> List[ReferenceDataTemplate]:
        items = self._scan_sorted("reference-templates", "created_at")
        templates = []
        for data in items:
            data["fields"] = [ReferenceField(**f) for f in data.get("fields", [])]
            data.setdefault("form_type_description", "")
            data.setdefault("created_by_name", "")
            data.setdefault("updated_at", None)
            templates.append(ReferenceDataTemplate(**data))
        return templates

    async def update_reference_template(self, template_id: str, name: Optional[str] = None,
                                        form_type_description: Optional[str] = None,
                                        fields: Optional[List[ReferenceField]] = None) -> bool:
        table = self._table("reference-templates")
        resp = table.get_item(Key={"id": template_id})
        if "Item" not in resp:
            return False
        expr_parts = ["updated_at = :ua"]
        values: Dict[str, Any] = {":ua": _now()}
        names = {}
        if name is not None:
            expr_parts.append("#n = :n")
            names["#n"] = "name"
            values[":n"] = name
        if form_type_description is not None:
            expr_parts.append("form_type_description = :ftd")
            values[":ftd"] = form_type_description
        if fields is not None:
            expr_parts.append("fields = :f")
            values[":f"] = [f.model_dump() for f in fields]
        update_kwargs = {"Key": {"id": template_id}, "UpdateExpression": "SET " + ", ".join(expr_parts),
                         "ExpressionAttributeValues": _to_decimal(values)}
        if names:
            update_kwargs["ExpressionAttributeNames"] = names
        table.update_item(**update_kwargs)
        return True

    async def delete_reference_template(self, template_id: str) -> bool:
        table = self._table("reference-templates")
        resp = table.get_item(Key={"id": template_id})
        if "Item" not in resp:
            return False
        table.delete_item(Key={"id": template_id})
        return True

    # ==================== Document Reference Data Operations ====================

    async def update_document_reference_data(self, batch_id: str, document_id: str,
                                             reference_data: List[Dict[str, str]],
                                             field_values: Dict[str, str]) -> bool:
        table = self._table("batches")
        resp = table.get_item(Key={"id": batch_id})
        if "Item" not in resp:
            return False
        data = _from_decimal(resp["Item"])
        documents = data.get("documents", [])
        found = False
        for d in documents:
            if d["id"] == document_id:
                d["reference_data"] = reference_data
                d["field_values"] = field_values
                found = True
                break
        if not found:
            return False
        table.update_item(Key={"id": batch_id}, UpdateExpression="SET documents = :docs",
                          ExpressionAttributeValues=_to_decimal({":docs": documents}))
        return True
