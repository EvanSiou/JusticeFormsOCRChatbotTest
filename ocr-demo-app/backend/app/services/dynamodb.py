"""DynamoDB service for sessions, config, prompts, and form types."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from ..config import get_settings

logger = logging.getLogger(__name__)

_dynamodb = None


def _get_resource():
    global _dynamodb
    if _dynamodb is None:
        settings = get_settings()
        kwargs = {"region_name": settings.aws_default_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        # Otherwise uses default credential chain (IAM role)
        _dynamodb = boto3.resource("dynamodb", **kwargs)
    return _dynamodb


def _table(name: str):
    return _get_resource().Table(name)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _to_decimal(obj):
    """Convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj


def _from_decimal(obj):
    """Convert Decimals back to floats."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_decimal(v) for v in obj]
    return obj


# ── Sessions ──

def create_session(data: dict) -> dict:
    settings = get_settings()
    session_id = str(uuid.uuid4())
    item = {
        "session_id": session_id,
        "status": "uploading",
        "created_at": _now(),
        **_to_decimal(data),
    }
    _table(settings.sessions_table).put_item(Item=item)
    return _from_decimal(item)


def get_session(session_id: str) -> Optional[dict]:
    settings = get_settings()
    resp = _table(settings.sessions_table).get_item(Key={"session_id": session_id})
    item = resp.get("Item")
    return _from_decimal(item) if item else None


def update_session(session_id: str, updates: dict):
    settings = get_settings()
    updates = _to_decimal(updates)
    expr_parts = []
    attr_names = {}
    attr_values = {}
    for i, (k, v) in enumerate(updates.items()):
        alias = f"#k{i}"
        val_alias = f":v{i}"
        expr_parts.append(f"{alias} = {val_alias}")
        attr_names[alias] = k
        attr_values[val_alias] = v
    _table(settings.sessions_table).update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


# ── Config ──

def get_config() -> dict:
    settings = get_settings()
    resp = _table(settings.config_table).get_item(Key={"config_key": "global"})
    item = resp.get("Item")
    if not item:
        # Return defaults
        return {
            "config_key": "global",
            "quality_threshold": 0.6,
            "default_model": "claude_bedrock",
        }
    return _from_decimal(item)


def save_config(config: dict):
    settings = get_settings()
    config["config_key"] = "global"
    _table(settings.config_table).put_item(Item=_to_decimal(config))


# ── Prompts ──

def list_prompts(prompt_type: Optional[str] = None) -> list:
    settings = get_settings()
    table = _table(settings.prompts_table)
    resp = table.scan()
    items = [_from_decimal(i) for i in resp.get("Items", [])]
    if prompt_type:
        items = [i for i in items if i.get("prompt_type") == prompt_type]
    return sorted(items, key=lambda x: x.get("name", ""))


def get_prompt(prompt_id: str) -> Optional[dict]:
    settings = get_settings()
    resp = _table(settings.prompts_table).get_item(Key={"prompt_id": prompt_id})
    item = resp.get("Item")
    return _from_decimal(item) if item else None


def create_prompt(data: dict) -> dict:
    settings = get_settings()
    prompt_id = str(uuid.uuid4())
    item = {"prompt_id": prompt_id, "created_at": _now(), **data}
    _table(settings.prompts_table).put_item(Item=item)
    return item


def update_prompt(prompt_id: str, data: dict):
    settings = get_settings()
    item = {"prompt_id": prompt_id, "updated_at": _now(), **data}
    _table(settings.prompts_table).put_item(Item=item)


def delete_prompt(prompt_id: str):
    settings = get_settings()
    _table(settings.prompts_table).delete_item(Key={"prompt_id": prompt_id})


# ── Form Types ──

def list_form_types() -> list:
    settings = get_settings()
    resp = _table(settings.form_types_table).scan()
    return [_from_decimal(i) for i in resp.get("Items", [])]


def get_form_type(form_type_id: str) -> Optional[dict]:
    settings = get_settings()
    resp = _table(settings.form_types_table).get_item(Key={"form_type_id": form_type_id})
    item = resp.get("Item")
    return _from_decimal(item) if item else None


def create_form_type(data: dict) -> dict:
    settings = get_settings()
    _table(settings.form_types_table).put_item(Item=data)
    return data


def delete_form_type(form_type_id: str):
    settings = get_settings()
    _table(settings.form_types_table).delete_item(Key={"form_type_id": form_type_id})
