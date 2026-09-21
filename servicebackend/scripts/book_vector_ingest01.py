"""OCR and embed the complete local pharmacology PDF into smart_long/pgvector.

Run from the repository root in the existing langGraph environment:
    conda run -n langGraph python servicebackend/scripts/book_vector_ingest01.py --dry-run
    conda run -n langGraph python servicebackend/scripts/book_vector_ingest01.py --run

The PDF and OCR page text remain local. Only chunks sent to the embedding API
leave the machine. Both OCR pages and embeddings are resumable in PostgreSQL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "servicebackend"
PDF_DIR = ROOT / "PDF"
OCR_SCRIPT = BACKEND / "scripts" / "book_ocr01.swift"
CHROMA_DIR = BACKEND / "book_vectors01"
REPORT_PATH = BACKEND / "book_vector_report02.json"
BOOK_ID = "pharmacology"
BOOK_TITLE = "药理学"
EDITION = "第九版"
MODEL = "qwen3.7-text-embedding-flash"
CHUNKER_VERSION = "page800-overlap100-v1"
DIMENSIONS = 1024
BATCH_SIZE = 10
PRICE_CNY_PER_TOKEN = 0.125 / 1_000_000


def clean_text(value: str) -> str:
    value = value.replace("\x00", "").replace("\u00ad", "")
    value = re.sub(r"[ \t]+", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def pdf_path() -> Path:
    matches = list(PDF_DIR.glob("药理学 第九版*.pdf"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one pharmacology PDF, found {len(matches)}")
    return matches[0]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def setup_tables(connection: psycopg.Connection) -> None:
    available = connection.execute(
        "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    if not available:
        raise RuntimeError("pgvector must be enabled in smart_long before ingestion")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_book_sources (
            book_id text PRIMARY KEY,
            book_title text NOT NULL,
            edition text NOT NULL,
            pdf_filename text NOT NULL,
            pdf_sha256 char(64) NOT NULL,
            total_pdf_pages integer NOT NULL,
            embedding_model text NOT NULL,
            embedding_dimension integer NOT NULL,
            chunker_version text NOT NULL,
            status text NOT NULL CHECK (status IN ('ingesting', 'ready')),
            api_tokens bigint NOT NULL DEFAULT 0,
            api_calls integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_book_pages (
            book_id text NOT NULL REFERENCES medical_book_sources(book_id),
            pdf_page integer NOT NULL CHECK (pdf_page > 0),
            page_text text NOT NULL,
            extraction text NOT NULL,
            PRIMARY KEY (book_id, pdf_page)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_book_chunks (
            chunk_id text PRIMARY KEY,
            book_id text NOT NULL,
            pdf_page integer NOT NULL,
            chunk_index integer NOT NULL,
            content text NOT NULL,
            extraction text NOT NULL,
            embedding_model text NOT NULL,
            embedding vector(1024) NOT NULL,
            FOREIGN KEY (book_id, pdf_page)
                REFERENCES medical_book_pages(book_id, pdf_page),
            UNIQUE (book_id, pdf_page, chunk_index)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS medical_book_chunks_book_page_idx "
        "ON medical_book_chunks (book_id, pdf_page)"
    )


def ensure_source(connection: psycopg.Connection, path: Path, sha: str, pages: int) -> None:
    row = connection.execute(
        """SELECT pdf_sha256, total_pdf_pages, embedding_model, embedding_dimension,
                  chunker_version FROM medical_book_sources WHERE book_id = %s""",
        (BOOK_ID,),
    ).fetchone()
    expected = (sha, pages, MODEL, DIMENSIONS, CHUNKER_VERSION)
    if row and tuple(row) != expected:
        raise RuntimeError(
            "An incompatible pharmacology source already exists; refusing to mix "
            "PDF versions, embedding models, or chunking strategies"
        )
    if not row:
        connection.execute(
            """
            INSERT INTO medical_book_sources
                (book_id, book_title, edition, pdf_filename, pdf_sha256,
                 total_pdf_pages, embedding_model, embedding_dimension,
                 chunker_version, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ingesting')
            """,
            (BOOK_ID, BOOK_TITLE, EDITION, path.name, sha, pages,
             MODEL, DIMENSIONS, CHUNKER_VERSION),
        )


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


def cache_pages(connection: psycopg.Connection, path: Path, reader: PdfReader) -> None:
    existing = {
        row[0] for row in connection.execute(
            "SELECT pdf_page FROM medical_book_pages WHERE book_id = %s", (BOOK_ID,)
        )
    }
    needs_ocr: list[int] = []
    for page in range(1, len(reader.pages) + 1):
        if page in existing:
            continue
        text = clean_text(reader.pages[page - 1].extract_text() or "")
        if len(text) < 100:
            needs_ocr.append(page)
            continue
        connection.execute(
            """INSERT INTO medical_book_pages (book_id, pdf_page, page_text, extraction)
               VALUES (%s, %s, %s, 'text_layer')""",
            (BOOK_ID, page, text),
        )

    for start, count in contiguous_spans(needs_ocr):
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
                    raise RuntimeError(f"OCR page order mismatch at PDF page {page}")
                text = clean_text(str(record["text"]))
                connection.execute(
                    """INSERT INTO medical_book_pages
                           (book_id, pdf_page, page_text, extraction)
                       VALUES (%s, %s, %s, 'macos_vision_ocr')""",
                    (BOOK_ID, page, text),
                )
                received += 1
                if received % 25 == 0:
                    print(f"OCR cached {received}/{count} pages in span", flush=True)
            error_text = process.stderr.read()
            if process.wait() != 0 or received != count:
                raise RuntimeError(
                    f"OCR stopped after {received}/{count} pages: {error_text[-1000:]}"
                )
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()


def build_pending(connection: psycopg.Connection) -> tuple[list[dict], int, list[int]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100,
        separators=["\n\n", "\n", "。", "；", "，", ""],
        length_function=len,
    )
    existing = {
        (page, index): chunk_id for page, index, chunk_id in connection.execute(
            """SELECT pdf_page, chunk_index, chunk_id FROM medical_book_chunks
               WHERE book_id = %s""",
            (BOOK_ID,),
        )
    }
    pending: list[dict] = []
    expected = 0
    empty_pages: list[int] = []
    for page, page_text, extraction in connection.execute(
        """SELECT pdf_page, page_text, extraction FROM medical_book_pages
           WHERE book_id = %s ORDER BY pdf_page""",
        (BOOK_ID,),
    ):
        page_chunks = 0
        for index, content in enumerate(splitter.split_text(page_text)):
            content = content.strip()
            if len(content) < 30:
                continue
            chunk_id = hashlib.sha256(
                f"{BOOK_ID}:{page}:{index}:{content}".encode("utf-8")
            ).hexdigest()[:24]
            expected += 1
            page_chunks += 1
            old_id = existing.get((page, index))
            if old_id and old_id != chunk_id:
                raise RuntimeError(
                    f"Existing PDF page {page} chunk {index} differs; "
                    "manual reindex is required"
                )
            if not old_id:
                pending.append({
                    "chunk_id": chunk_id,
                    "page": page,
                    "index": index,
                    "content": content,
                    "extraction": extraction,
                })
        if page_chunks == 0:
            empty_pages.append(page)
    return pending, expected, empty_pages


def prior_chroma_vectors() -> dict[str, list[float]]:
    if not CHROMA_DIR.exists():
        return {}
    try:
        import chromadb

        collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(
            "medical_books_trial01"
        )
        result = collection.get(where={"book_id": BOOK_ID}, include=["embeddings"])
        return {
            chunk_id: [float(value) for value in vector]
            for chunk_id, vector in zip(result["ids"], result["embeddings"])
        }
    except Exception as exc:
        print(f"Prior Chroma vectors unavailable; re-embedding needed: {exc}", flush=True)
        return {}


def insert_chunks(connection: psycopg.Connection, batch: list[dict], vectors: list[list[float]],
                  tokens: int = 0, api_call: bool = False) -> None:
    from app.RAG.book_rag import vector_literal

    if len(batch) != len(vectors):
        raise RuntimeError("Embedding count does not match chunk count")
    with connection.transaction():
        for chunk, vector in zip(batch, vectors):
            connection.execute(
                """
                INSERT INTO medical_book_chunks
                    (chunk_id, book_id, pdf_page, chunk_index, content,
                     extraction, embedding_model, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (chunk["chunk_id"], BOOK_ID, chunk["page"], chunk["index"],
                 chunk["content"], chunk["extraction"], MODEL,
                 vector_literal(vector)),
            )
        if api_call:
            connection.execute(
                """UPDATE medical_book_sources SET api_tokens = api_tokens + %s,
                          api_calls = api_calls + 1, updated_at = now()
                   WHERE book_id = %s""",
                (tokens, BOOK_ID),
            )


def embed_pending(connection: psycopg.Connection, pending: list[dict],
                  max_cost_cny: float) -> int:
    from app.RAG.book_rag import embedding_client

    prior = prior_chroma_vectors()
    reused = 0
    new_chunks: list[dict] = []
    for chunk in pending:
        vector = prior.get(chunk["chunk_id"])
        if vector is None:
            new_chunks.append(chunk)
        else:
            insert_chunks(connection, [chunk], [vector])
            reused += 1
    print(f"Reused {reused} Chroma vectors; new embeddings needed: {len(new_chunks)}", flush=True)
    if not new_chunks:
        return reused

    client = embedding_client()
    for offset in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[offset:offset + BATCH_SIZE]
        billed = connection.execute(
            "SELECT api_tokens FROM medical_book_sources WHERE book_id = %s", (BOOK_ID,)
        ).fetchone()[0]
        conservative_next_tokens = 2 * sum(len(chunk["content"]) for chunk in batch)
        if (billed + conservative_next_tokens) * PRICE_CNY_PER_TOKEN > max_cost_cny:
            raise RuntimeError(
                f"Embedding cost cap ¥{max_cost_cny:.2f} reached before batch "
                f"{offset // BATCH_SIZE + 1}; committed chunks are safe to resume"
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
        insert_chunks(connection, batch, vectors, tokens, api_call=True)
        if (offset // BATCH_SIZE + 1) % 10 == 0 or offset + len(batch) == len(new_chunks):
            print(f"Embedded {offset + len(batch)}/{len(new_chunks)} new chunks", flush=True)
    return reused


def summarize(connection: psycopg.Connection, expected: int, empty_pages: list[int],
              reused: int, path: Path) -> dict:
    page_count, with_text, ocr_count = connection.execute(
        """SELECT count(*), count(*) FILTER (WHERE length(page_text) >= 30),
                  count(*) FILTER (WHERE extraction = 'macos_vision_ocr')
           FROM medical_book_pages WHERE book_id = %s""",
        (BOOK_ID,),
    ).fetchone()
    chunks = connection.execute(
        "SELECT count(*) FROM medical_book_chunks WHERE book_id = %s", (BOOK_ID,)
    ).fetchone()[0]
    api_tokens, api_calls, status = connection.execute(
        """SELECT api_tokens, api_calls, status FROM medical_book_sources
           WHERE book_id = %s""",
        (BOOK_ID,),
    ).fetchone()
    return {
        "book_id": BOOK_ID,
        "book_title": BOOK_TITLE,
        "edition": EDITION,
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
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--max-cost-cny", type=float, default=0.20)
    args = parser.parse_args()
    if args.max_cost_cny <= 0:
        parser.error("--max-cost-cny must be positive")

    path = pdf_path()
    config = dotenv_values(BACKEND / ".env")
    if config.get("EMBEDDING_MODEL") != MODEL:
        raise RuntimeError("Configured embedding model differs from the trial model")
    database_url = config.get("POSTGRES_LONG_TERM_URL")
    if not database_url:
        raise RuntimeError("POSTGRES_LONG_TERM_URL is missing")
    reader = PdfReader(path)
    sha = file_sha256(path)
    print(f"Source: {path.name}, PDF pages: {len(reader.pages)}, SHA-256: {sha[:12]}...", flush=True)
    if args.dry_run:
        with psycopg.connect(database_url, options="-c default_transaction_read_only=on") as conn:
            print("pgvector installed:", bool(conn.execute(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()))
        return

    if not config.get("DASHSCOPE_API_KEY"):
        raise RuntimeError("DASHSCOPE_API_KEY is missing")
    with psycopg.connect(database_url, autocommit=True) as conn:
        setup_tables(conn)
        ensure_source(conn, path, sha, len(reader.pages))
        cache_pages(conn, path, reader)
        cached_pages = conn.execute(
            "SELECT count(*) FROM medical_book_pages WHERE book_id = %s", (BOOK_ID,)
        ).fetchone()[0]
        if cached_pages != len(reader.pages):
            raise RuntimeError(f"Only {cached_pages}/{len(reader.pages)} PDF pages were cached")
        pending, expected, empty_pages = build_pending(conn)
        print(f"Expected chunks: {expected}; pending: {len(pending)}", flush=True)
        reused = embed_pending(conn, pending, args.max_cost_cny)
        actual = conn.execute(
            "SELECT count(*) FROM medical_book_chunks WHERE book_id = %s", (BOOK_ID,)
        ).fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"Only {actual}/{expected} chunks are stored")
        conn.execute(
            """UPDATE medical_book_sources SET status = 'ready', updated_at = now()
               WHERE book_id = %s""",
            (BOOK_ID,),
        )
        report = summarize(conn, expected, empty_pages, reused, path)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Ready: {report['stored_chunks']} chunks, {report['ocr_pages']} OCR pages; "
          f"estimated embedding price ¥{report['estimated_embedding_list_price_cny']}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(BACKEND))
    main()
