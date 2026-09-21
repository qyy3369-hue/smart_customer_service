"""Embed complete internal-medicine or diagnostics textbooks into smart_long.

The PDF stays local. Pages with an unusable text layer are OCR'd in memory with
macOS Vision. Only text chunks sent for embedding leave the machine. PostgreSQL
stores page text, vectors, provenance, token usage, and resumable progress.

Run from the repository root using the existing langGraph environment:
    conda run -n langGraph python servicebackend/scripts/book_vector_ingest.py --book internal_medicine --dry-run
    conda run --no-capture-output -n langGraph python -u servicebackend/scripts/book_vector_ingest.py --book internal_medicine --run --max-cost-cny 0.35
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "servicebackend"
sys.path.insert(0, str(BACKEND))

from app.RAG.embedding import embedding_client, vector_literal  # noqa: E402


PDF_DIR = ROOT / "PDF"
OCR_SCRIPT = BACKEND / "scripts" / "book_ocr01.swift"
CHROMA_DIR = BACKEND / "book_vectors01"
MODEL = "qwen3.7-text-embedding-flash"
CHUNKER_VERSION = "page800-overlap100-v1"
DIMENSIONS = 1024
BATCH_SIZE = 10
PRICE_CNY_PER_TOKEN = 0.125 / 1_000_000


@dataclass(frozen=True)
class Book:
    book_id: str
    title: str
    edition: str
    pdf_prefix: str
    report_name: str


BOOKS = {
    "internal_medicine": Book(
        "internal_medicine", "内科学", "第10版", "内科学第10版", "book_vector_report03.json"
    ),
    "diagnostics": Book(
        "diagnostics", "诊断学", "第9版", "诊断学", "book_vector_report04.json"
    ),
}


def pdf_path(book: Book) -> Path:
    matches = list(PDF_DIR.glob(f"{book.pdf_prefix}*.pdf"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one PDF for {book.title}, found {len(matches)}")
    return matches[0]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(value: str) -> str:
    value = value.replace("\u00ad", "")
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def needs_ocr(text: str) -> bool:
    # A Chinese textbook page that has almost no Han characters is often a
    # malformed/partial text layer. OCR it rather than embedding gibberish.
    han_count = sum("\u4e00" <= char <= "\u9fff" for char in text)
    return len(text) < 100 or han_count < 20


def contiguous_spans(numbers: list[int]) -> list[tuple[int, int]]:
    if not numbers:
        return []
    spans: list[tuple[int, int]] = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number != previous + 1:
            spans.append((start, previous - start + 1))
            start = number
        previous = number
    spans.append((start, previous - start + 1))
    return spans


def ensure_schema(connection: psycopg.Connection) -> None:
    if not connection.execute(
        "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
    ).fetchone():
        raise RuntimeError("pgvector is not installed in smart_long")
    required = ("medical_book_sources", "medical_book_pages", "medical_book_chunks")
    missing = [name for name in required if not connection.execute(
        "SELECT to_regclass(%s)", (name,)
    ).fetchone()[0]]
    if missing:
        raise RuntimeError(f"Missing textbook tables: {missing}")


def ensure_source(connection: psycopg.Connection, book: Book, path: Path,
                  sha: str, pages: int) -> None:
    row = connection.execute(
        """SELECT pdf_sha256, total_pdf_pages, embedding_model, embedding_dimension,
                  chunker_version FROM medical_book_sources WHERE book_id = %s""",
        (book.book_id,),
    ).fetchone()
    expected = (sha, pages, MODEL, DIMENSIONS, CHUNKER_VERSION)
    if row and tuple(row) != expected:
        raise RuntimeError(
            f"Existing {book.title} source uses another PDF, model, or chunker; "
            "refusing to mix incompatible vectors"
        )
    if not row:
        connection.execute(
            """INSERT INTO medical_book_sources
                   (book_id, book_title, edition, pdf_filename, pdf_sha256,
                    total_pdf_pages, embedding_model, embedding_dimension,
                    chunker_version, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ingesting')""",
            (book.book_id, book.title, book.edition, path.name, sha, pages,
             MODEL, DIMENSIONS, CHUNKER_VERSION),
        )


def cache_pages(connection: psycopg.Connection, book: Book,
                path: Path, reader: PdfReader) -> None:
    existing = {
        row[0] for row in connection.execute(
            "SELECT pdf_page FROM medical_book_pages WHERE book_id = %s", (book.book_id,)
        )
    }
    needs_vision: list[int] = []
    text_layer_count = 0
    for page in range(1, len(reader.pages) + 1):
        if page in existing:
            continue
        text = clean_text(reader.pages[page - 1].extract_text() or "")
        if needs_ocr(text):
            needs_vision.append(page)
        else:
            connection.execute(
                """INSERT INTO medical_book_pages
                       (book_id, pdf_page, page_text, extraction)
                   VALUES (%s, %s, %s, 'text_layer')""",
                (book.book_id, page, text),
            )
            text_layer_count += 1
    print(f"{book.title}: cached {text_layer_count} text-layer pages; "
          f"{len(needs_vision)} pages need local OCR", flush=True)

    for start, count in contiguous_spans(needs_vision):
        print(f"OCR PDF pages {start}-{start + count - 1}", flush=True)
        process = subprocess.Popen(
            ["xcrun", "swift", str(OCR_SCRIPT), str(path), str(start), str(count)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        assert process.stdout is not None and process.stderr is not None
        received = 0
        try:
            for line in process.stdout:
                record = json.loads(line)
                page = int(record["page"])
                if page != start + received:
                    raise RuntimeError(f"OCR page order mismatch at {page}")
                connection.execute(
                    """INSERT INTO medical_book_pages
                           (book_id, pdf_page, page_text, extraction)
                       VALUES (%s, %s, %s, 'macos_vision_ocr')""",
                    (book.book_id, page, clean_text(str(record["text"]))),
                )
                received += 1
            error_text = process.stderr.read()
            if process.wait() != 0 or received != count:
                raise RuntimeError(
                    f"OCR stopped after {received}/{count} pages: {error_text[-1000:]}"
                )
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()


def build_pending(connection: psycopg.Connection, book: Book) -> tuple[list[dict], int, list[int]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100,
        separators=["\n\n", "\n", "。", "；", "，", ""],
        length_function=len,
    )
    existing = {
        (page, index): chunk_id for page, index, chunk_id in connection.execute(
            """SELECT pdf_page, chunk_index, chunk_id FROM medical_book_chunks
               WHERE book_id = %s""",
            (book.book_id,),
        )
    }
    pending: list[dict] = []
    expected = 0
    empty_pages: list[int] = []
    for page, text, extraction in connection.execute(
        """SELECT pdf_page, page_text, extraction FROM medical_book_pages
           WHERE book_id = %s ORDER BY pdf_page""",
        (book.book_id,),
    ):
        page_chunks = 0
        for index, content in enumerate(splitter.split_text(text)):
            content = content.strip()
            if len(content) < 30:
                continue
            chunk_id = hashlib.sha256(
                f"{book.book_id}:{page}:{index}:{content}".encode("utf-8")
            ).hexdigest()[:24]
            old_id = existing.get((page, index))
            if old_id and old_id != chunk_id:
                raise RuntimeError(f"PDF page {page} chunk {index} changed; manual reindex needed")
            if not old_id:
                pending.append({
                    "chunk_id": chunk_id,
                    "page": page,
                    "index": index,
                    "content": content,
                    "extraction": extraction,
                })
            expected += 1
            page_chunks += 1
        if page_chunks == 0:
            empty_pages.append(page)
    return pending, expected, empty_pages


def prior_chroma_vectors(book: Book) -> dict[str, list[float]]:
    if not CHROMA_DIR.exists():
        return {}
    try:
        import chromadb

        collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(
            "medical_books_trial01"
        )
        if collection.metadata.get("embedding_model") != MODEL:
            raise RuntimeError("Chroma trial used a different embedding model")
        result = collection.get(where={"book_id": book.book_id}, include=["embeddings"])
        return {
            chunk_id: [float(value) for value in vector]
            for chunk_id, vector in zip(result["ids"], result["embeddings"])
        }
    except Exception as exc:
        print(f"Trial vectors unavailable; embedding all new chunks: {exc}", flush=True)
        return {}


def insert_batch(connection: psycopg.Connection, book: Book, chunks: list[dict],
                 vectors: list[list[float]], tokens: int = 0,
                 api_call: bool = False) -> None:
    if len(chunks) != len(vectors):
        raise RuntimeError("Embedding count does not match chunk count")
    with connection.transaction():
        for chunk, vector in zip(chunks, vectors):
            connection.execute(
                """INSERT INTO medical_book_chunks
                       (chunk_id, book_id, pdf_page, chunk_index, content,
                        extraction, embedding_model, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)""",
                (chunk["chunk_id"], book.book_id, chunk["page"], chunk["index"],
                 chunk["content"], chunk["extraction"], MODEL,
                 vector_literal(vector)),
            )
        if api_call:
            connection.execute(
                """UPDATE medical_book_sources SET api_tokens = api_tokens + %s,
                          api_calls = api_calls + 1, updated_at = now()
                   WHERE book_id = %s""",
                (tokens, book.book_id),
            )


def embed_pending(connection: psycopg.Connection, book: Book, pending: list[dict],
                  max_cost_cny: float) -> int:
    prior = prior_chroma_vectors(book)
    reused = 0
    new: list[dict] = []
    for chunk in pending:
        vector = prior.get(chunk["chunk_id"])
        if vector is None:
            new.append(chunk)
        else:
            insert_batch(connection, book, [chunk], [vector])
            reused += 1
    print(f"{book.title}: reused {reused} trial vectors; "
          f"{len(new)} new embeddings needed", flush=True)
    if not new:
        return reused

    client = embedding_client()
    for offset in range(0, len(new), BATCH_SIZE):
        batch = new[offset:offset + BATCH_SIZE]
        billed = connection.execute(
            "SELECT api_tokens FROM medical_book_sources WHERE book_id = %s",
            (book.book_id,),
        ).fetchone()[0]
        conservative_next_tokens = 2 * sum(len(chunk["content"]) for chunk in batch)
        if (billed + conservative_next_tokens) * PRICE_CNY_PER_TOKEN > max_cost_cny:
            raise RuntimeError(
                f"{book.title} embedding budget ¥{max_cost_cny:.2f} reached; "
                "completed batches are safe to resume"
            )
        response = client.embeddings.create(
            model=MODEL, input=[chunk["content"] for chunk in batch]
        )
        if len(response.data) != len(batch) or not response.usage:
            raise RuntimeError("Embedding API returned incomplete data or no token usage")
        tokens = response.usage.total_tokens or response.usage.prompt_tokens
        if tokens is None:
            raise RuntimeError("Embedding API omitted token usage")
        vectors = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        insert_batch(connection, book, batch, vectors, tokens, api_call=True)
        if (offset // BATCH_SIZE + 1) % 10 == 0 or offset + len(batch) == len(new):
            print(f"{book.title}: embedded {offset + len(batch)}/{len(new)}", flush=True)
    return reused


def summarize(connection: psycopg.Connection, book: Book, expected: int,
              empty_pages: list[int], reused: int, path: Path) -> dict:
    page_count, with_text, ocr_count = connection.execute(
        """SELECT count(*), count(*) FILTER (WHERE length(page_text) >= 30),
                  count(*) FILTER (WHERE extraction = 'macos_vision_ocr')
           FROM medical_book_pages WHERE book_id = %s""",
        (book.book_id,),
    ).fetchone()
    chunks = connection.execute(
        "SELECT count(*) FROM medical_book_chunks WHERE book_id = %s",
        (book.book_id,),
    ).fetchone()[0]
    api_tokens, api_calls, status = connection.execute(
        """SELECT api_tokens, api_calls, status FROM medical_book_sources
           WHERE book_id = %s""",
        (book.book_id,),
    ).fetchone()
    return {
        "book_id": book.book_id,
        "book_title": book.title,
        "edition": book.edition,
        "source_pdf": path.name,
        "pdf_pages": page_count,
        "pages_with_at_least_30_characters": with_text,
        "ocr_pages": ocr_count,
        "pages_without_chunks": empty_pages,
        "expected_chunks": expected,
        "stored_chunks": chunks,
        "reused_chroma_vectors_this_run": reused,
        "embedding_model": MODEL,
        "embedding_dimension": DIMENSIONS,
        "api_tokens_recorded": api_tokens,
        "api_calls_recorded": api_calls,
        "estimated_embedding_list_price_cny": round(api_tokens * PRICE_CNY_PER_TOKEN, 6),
        "billing_note": "List-price estimate; free quota/discounts and query/LLM costs excluded.",
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=BOOKS)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--max-cost-cny", type=float, default=0.35)
    args = parser.parse_args()
    if args.max_cost_cny <= 0:
        parser.error("--max-cost-cny must be positive")

    book = BOOKS[args.book]
    path = pdf_path(book)
    config = dotenv_values(BACKEND / ".env")
    if config.get("EMBEDDING_MODEL") != MODEL:
        raise RuntimeError("Configured embedding model differs from the trial model")
    database_url = config.get("POSTGRES_LONG_TERM_URL")
    if not database_url:
        raise RuntimeError("POSTGRES_LONG_TERM_URL is missing")
    reader = PdfReader(path)
    sha = file_sha256(path)
    print(f"{book.title} {book.edition}: {len(reader.pages)} PDF pages, "
          f"SHA-256 {sha[:12]}...", flush=True)
    if args.dry_run:
        with psycopg.connect(database_url, options="-c default_transaction_read_only=on") as conn:
            ensure_schema(conn)
            row = conn.execute(
                """SELECT status, api_tokens FROM medical_book_sources
                   WHERE book_id = %s""",
                (book.book_id,),
            ).fetchone()
            print("Existing source:", row, flush=True)
        return
    if not config.get("DASHSCOPE_API_KEY"):
        raise RuntimeError("DASHSCOPE_API_KEY is missing")

    with psycopg.connect(database_url, autocommit=True) as conn:
        ensure_schema(conn)
        ensure_source(conn, book, path, sha, len(reader.pages))
        cache_pages(conn, book, path, reader)
        cached_pages = conn.execute(
            "SELECT count(*) FROM medical_book_pages WHERE book_id = %s",
            (book.book_id,),
        ).fetchone()[0]
        if cached_pages != len(reader.pages):
            raise RuntimeError(f"Only {cached_pages}/{len(reader.pages)} pages were cached")
        pending, expected, empty_pages = build_pending(conn, book)
        print(f"{book.title}: {expected} expected chunks; {len(pending)} pending", flush=True)
        reused = embed_pending(conn, book, pending, args.max_cost_cny)
        actual = conn.execute(
            "SELECT count(*) FROM medical_book_chunks WHERE book_id = %s",
            (book.book_id,),
        ).fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"Only {actual}/{expected} chunks are stored")
        conn.execute(
            """UPDATE medical_book_sources SET status = 'ready', updated_at = now()
               WHERE book_id = %s""",
            (book.book_id,),
        )
        report = summarize(conn, book, expected, empty_pages, reused, path)
    report_path = BACKEND / book.report_name
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{book.title}: ready, {report['stored_chunks']} chunks, "
          f"{report['ocr_pages']} OCR pages; estimated new embedding price "
          f"¥{report['estimated_embedding_list_price_cny']}", flush=True)
    print(f"Report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
