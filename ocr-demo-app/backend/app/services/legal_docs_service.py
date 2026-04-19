import logging
from pathlib import Path
from typing import List

import fitz
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import get_settings
from .vector_store import get_legal_db, add_legal_documents


logger = logging.getLogger(__name__)
settings = get_settings()


def clean_legal_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = " ".join(text.split())
    return text.strip()


def load_legal_documents() -> List[Document]:
    docs: List[Document] = []
    legal_dir = Path(settings.legal_docs_dir)
    legal_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(legal_dir.glob("*.pdf"))
    for pdf_path in pdf_files:
        pdf = fitz.open(str(pdf_path))
        for page_idx in range(pdf.page_count):
            page = pdf.load_page(page_idx)
            text = clean_legal_text(page.get_text("text"))
            if not text:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source_type": "legal_doc",
                        "source_name": pdf_path.name,
                        "page": page_idx + 1,
                    },
                )
            )
        pdf.close()

    return docs


def chunk_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.text_chunk_size,
        chunk_overlap=settings.text_chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(documents)


def ensure_legal_docs_indexed() -> None:
    db = get_legal_db()

    try:
        count = db._collection.count()
    except Exception:
        count = 0

    if count > 0:
        logger.info("Legal docs already indexed. Count=%s", count)
        return

    docs = load_legal_documents()
    if not docs:
        logger.warning("No legal PDFs found in %s", settings.legal_docs_dir)
        return

    chunks = chunk_documents(docs)
    add_legal_documents(chunks)
    logger.info("Indexed %s legal document chunks.", len(chunks))
