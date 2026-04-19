from pathlib import Path
from threading import Lock
from typing import List

from langchain_core.documents import Document
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.vectorstores import Chroma

from ..config import get_settings


_settings = get_settings()
_lock = Lock()

_legal_db = None
_session_db = None
_embeddings = None

CHROMA_ROOT = Path(_settings.chroma_dir)
LEGAL_COLLECTION = "legal_docs"
SESSION_COLLECTION = "ocr_sessions"


def _ensure_dirs() -> None:
    CHROMA_ROOT.mkdir(parents=True, exist_ok=True)


def get_embeddings() -> FastEmbedEmbeddings:
    global _embeddings
    with _lock:
        if _embeddings is None:
            _embeddings = FastEmbedEmbeddings()
    return _embeddings


def get_legal_db() -> Chroma:
    global _legal_db
    _ensure_dirs()
    with _lock:
        if _legal_db is None:
            _legal_db = Chroma(
                collection_name=LEGAL_COLLECTION,
                persist_directory=str(CHROMA_ROOT),
                embedding_function=get_embeddings(),
            )
    return _legal_db


def get_session_db() -> Chroma:
    global _session_db
    _ensure_dirs()
    with _lock:
        if _session_db is None:
            _session_db = Chroma(
                collection_name=SESSION_COLLECTION,
                persist_directory=str(CHROMA_ROOT),
                embedding_function=get_embeddings(),
            )
    return _session_db


def add_legal_documents(documents: List[Document]) -> None:
    if not documents:
        return
    db = get_legal_db()
    db.add_documents(documents)


def add_session_documents(documents: List[Document]) -> None:
    if not documents:
        return
    db = get_session_db()
    db.add_documents(documents)


def delete_session_documents(session_id: str) -> None:
    db = get_session_db()
    try:
        db._collection.delete(where={"session_id": session_id})
    except Exception:
        pass


def search_legal(question: str, k: int) -> List[Document]:
    db = get_legal_db()
    return db.similarity_search(question, k=k)


def search_session(session_id: str, question: str, k: int) -> List[Document]:
    db = get_session_db()
    return db.similarity_search(
        question,
        k=k,
        filter={"session_id": session_id},
    )
