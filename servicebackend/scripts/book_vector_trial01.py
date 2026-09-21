"""Small, cost-capped embedding trial for three local medical textbooks.

Run from the repository root with the existing langGraph environment:
    conda run -n langGraph python servicebackend/scripts/book_vector_trial01.py --dry-run
    conda run -n langGraph python servicebackend/scripts/book_vector_trial01.py --run

The PDF files stay local. Only extracted text chunks are sent to DashScope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "servicebackend"
PDF_DIR = ROOT / "PDF"
VECTOR_DIR = BACKEND / "book_vectors01"
REPORT_PATH = BACKEND / "book_vector_report01.json"
OCR_SCRIPT = BACKEND / "scripts" / "book_ocr01.swift"
START_PAGE = 100  # PDF page number, not printed book page number
PAGE_COUNT = 20
BATCH_SIZE = 10
MAX_COST_CNY = 0.10
MODEL = "qwen3.7-text-embedding-flash"
PRICE_CNY_PER_1000_TOKENS = 0.000125  # Beijing, synchronous API, list price
BOOKS = (
    ("内科学第10版", "internal_medicine", "内科学", "第10版"),
    ("诊断学", "diagnostics", "诊断学", "版次待核实"),
    ("药理学", "pharmacology", "药理学", "第九版"),
)
QUERIES = {
    "internal_medicine": "肺脓肿有哪些临床表现？",
    "diagnostics": "问诊中应避免哪些不恰当提问？",
    "pharmacology": "M胆碱受体阻断药有哪些解痉药？",
}


def ocr_pages(pdf_path: Path, start: int, count: int) -> dict[int, str]:
    result = subprocess.run(
        ["xcrun", "swift", str(OCR_SCRIPT), str(pdf_path), str(start), str(count)],
        check=True,
        capture_output=True,
        text=True,
    )
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if len(records) != count:
        raise RuntimeError(f"OCR returned {len(records)} of {count} requested pages")
    return {int(record["page"]): str(record["text"]) for record in records}


def clean_text(value: str) -> str:
    value = value.replace("\x00", "").replace("\u00ad", "")
    value = re.sub(r"[ \t]+", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def load_page_texts(pdf_path: Path) -> tuple[dict[int, str], dict[int, str]]:
    reader = PdfReader(pdf_path)
    end_page = START_PAGE + PAGE_COUNT - 1
    if len(reader.pages) < end_page:
        raise RuntimeError(f"{pdf_path.name} has only {len(reader.pages)} pages")
    pages = {
        page: clean_text(reader.pages[page - 1].extract_text() or "")
        for page in range(START_PAGE, end_page + 1)
    }
    methods = {page: "text_layer" for page in pages}
    missing = [page for page, text in pages.items() if len(text) < 100]
    if len(missing) >= PAGE_COUNT // 2:
        print(f"OCR {pdf_path.name}: {START_PAGE}-{end_page}", flush=True)
        pages.update({page: clean_text(text) for page, text in ocr_pages(pdf_path, START_PAGE, PAGE_COUNT).items()})
        methods.update({page: "macos_vision_ocr" for page in pages})
    else:
        for page in missing:
            print(f"OCR sparse page {pdf_path.name}: {page}", flush=True)
            pages.update({p: clean_text(t) for p, t in ocr_pages(pdf_path, page, 1).items()})
            methods[page] = "macos_vision_ocr"
    return pages, methods


def build_chunks() -> tuple[list[dict], list[dict]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "；", "，", ""],
        length_function=len,
    )
    chunks: list[dict] = []
    summaries: list[dict] = []
    for prefix, book_id, title, edition in BOOKS:
        matches = list(PDF_DIR.glob(f"{prefix}*.pdf"))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one PDF starting with {prefix}, found {len(matches)}")
        path = matches[0]
        pages, methods = load_page_texts(path)
        summary = {
            "book_id": book_id,
            "title": title,
            "edition": edition,
            "source_pdf": path.name,
            "pdf_pages": [START_PAGE, START_PAGE + PAGE_COUNT - 1],
            "pages_with_text": sum(bool(text) for text in pages.values()),
            "pages_indexed": 0,
            "pages_without_chunks": [],
            "ocr_pages": sum(method == "macos_vision_ocr" for method in methods.values()),
            "characters": sum(len(text) for text in pages.values()),
            "chunks": 0,
            "new_chunks": 0,
            "reused_chunks": 0,
            "api_tokens": 0,
            "estimated_list_price_cny": 0.0,
        }
        for page, text in pages.items():
            if not text:
                summary["pages_without_chunks"].append(page)
                continue
            page_chunks = 0
            for index, chunk_text in enumerate(splitter.split_text(text)):
                chunk_text = chunk_text.strip()
                if len(chunk_text) < 30:
                    continue
                digest = hashlib.sha256(
                    f"{book_id}:{page}:{index}:{chunk_text}".encode("utf-8")
                ).hexdigest()[:24]
                chunks.append({
                    "id": digest,
                    "text": chunk_text,
                    "metadata": {
                        "book_id": book_id,
                        "book_title": title,
                        "edition": edition,
                        "source_pdf": path.name,
                        "pdf_page": page,
                        "chunk_index": index,
                        "extraction": methods[page],
                        "embedding_model": MODEL,
                    },
                })
                summary["chunks"] += 1
                page_chunks += 1
            if page_chunks:
                summary["pages_indexed"] += 1
            else:
                summary["pages_without_chunks"].append(page)
        print(
            f"{title}: pages={PAGE_COUNT}, OCR={summary['ocr_pages']}, "
            f"characters={summary['characters']}, chunks={summary['chunks']}",
            flush=True,
        )
        summaries.append(summary)
    return chunks, summaries


def run_trial(chunks: list[dict], summaries: list[dict]) -> dict:
    import chromadb
    from chromadb.config import Settings
    from openai import OpenAI

    config = dotenv_values(BACKEND / ".env")
    api_key = config.get("DASHSCOPE_API_KEY")
    configured_model = config.get("EMBEDDING_MODEL") or MODEL
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is missing from servicebackend/.env")
    if configured_model != MODEL:
        raise RuntimeError(f"Configured embedding model {configured_model!r} is not the cost-capped trial model {MODEL!r}")

    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=60.0,
        max_retries=1,
    )
    chroma = chromadb.PersistentClient(
        path=str(VECTOR_DIR), settings=Settings(anonymized_telemetry=False)
    )
    collection = chroma.get_or_create_collection(
        name="medical_books_trial01", metadata={"embedding_model": MODEL}
    )
    if collection.metadata.get("embedding_model") != MODEL:
        raise RuntimeError("Existing collection uses a different embedding model")

    summary_by_id = {summary["book_id"]: summary for summary in summaries}
    existing_ids = set(collection.get(ids=[chunk["id"] for chunk in chunks], include=[])["ids"])
    pending = [chunk for chunk in chunks if chunk["id"] not in existing_ids]
    for chunk in chunks:
        if chunk["id"] in existing_ids:
            summary_by_id[chunk["metadata"]["book_id"]]["reused_chunks"] += 1
    total_tokens = 0
    api_calls = 0
    for offset in range(0, len(pending), BATCH_SIZE):
        batch = pending[offset : offset + BATCH_SIZE]
        texts = [item["text"] for item in batch]
        conservative_next_tokens = 2 * sum(len(text) for text in texts)
        projected_cost = (total_tokens + conservative_next_tokens) * PRICE_CNY_PER_1000_TOKENS / 1000
        if projected_cost > MAX_COST_CNY:
            raise RuntimeError(f"Cost cap would be exceeded before batch {offset // BATCH_SIZE + 1}; {offset} chunks already embedded")
        response = client.embeddings.create(model=MODEL, input=texts)
        if len(response.data) != len(batch) or not response.usage:
            raise RuntimeError("Embedding API did not return expected vectors or token usage")
        usage_tokens = response.usage.total_tokens or response.usage.prompt_tokens
        if usage_tokens is None:
            raise RuntimeError("Embedding API did not report tokens")
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if any(len(vector) != 1024 for vector in vectors):
            raise RuntimeError("Unexpected embedding dimension")
        collection.add(
            ids=[item["id"] for item in batch],
            documents=texts,
            metadatas=[item["metadata"] for item in batch],
            embeddings=vectors,
        )
        total_tokens += usage_tokens
        api_calls += 1
        for book_id in {item["metadata"]["book_id"] for item in batch}:
            selected = [item for item in batch if item["metadata"]["book_id"] == book_id]
            summary_by_id[book_id]["new_chunks"] += len(selected)
            # The API reports batch-level usage, so distribute it by character share.
            fraction = sum(len(item["text"]) for item in selected) / sum(len(text) for text in texts)
            summary_by_id[book_id]["api_tokens"] += round(usage_tokens * fraction)
        print(f"Embedded {offset + len(batch)}/{len(pending)} new chunks, cumulative tokens={total_tokens}", flush=True)

    retrieval_checks = []
    for book_id, query in QUERIES.items():
        projected_cost = (total_tokens + 2 * len(query)) * PRICE_CNY_PER_1000_TOKENS / 1000
        if projected_cost > MAX_COST_CNY:
            raise RuntimeError("Cost cap would be exceeded by retrieval check")
        response = client.embeddings.create(model=MODEL, input=[query])
        query_tokens = response.usage.total_tokens or response.usage.prompt_tokens or 0
        total_tokens += query_tokens
        api_calls += 1
        result = collection.query(
            query_embeddings=[response.data[0].embedding],
            n_results=3,
            where={"book_id": book_id},
            include=["metadatas", "distances"],
        )
        retrieval_checks.append({
            "book_id": book_id,
            "query": query,
            "query_tokens": query_tokens,
            "hits": [
                {"pdf_page": meta["pdf_page"], "distance": round(float(distance), 4)}
                for meta, distance in zip(result["metadatas"][0], result["distances"][0])
            ],
        })
    for summary in summaries:
        summary["estimated_list_price_cny"] = round(
            summary["api_tokens"] * PRICE_CNY_PER_1000_TOKENS / 1000, 6
        )
    return {
        "model": MODEL,
        "embedding_dimension": 1024,
        "price_cny_per_1000_tokens": PRICE_CNY_PER_1000_TOKENS,
        "max_cost_cny": MAX_COST_CNY,
        "page_numbering": "1-based PDF page number; may differ from printed textbook page",
        "api_calls": api_calls,
        "api_tokens_total_including_queries": total_tokens,
        "estimated_list_price_cny": round(total_tokens * PRICE_CNY_PER_1000_TOKENS / 1000, 6),
        "billing_note": "List-price estimate, not actual charge; free quota and account discounts may apply.",
        "vector_store": str(VECTOR_DIR),
        "collection": collection.name,
        "collection_count": collection.count(),
        "books": summaries,
        "retrieval_checks": retrieval_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    chunks, summaries = build_chunks()
    if args.dry_run:
        print(json.dumps({"books": summaries, "total_chunks": len(chunks)}, ensure_ascii=False, indent=2))
        return
    report = run_trial(chunks, summaries)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {REPORT_PATH}", flush=True)
    print(json.dumps({
        "api_tokens": report["api_tokens_total_including_queries"],
        "estimated_list_price_cny": report["estimated_list_price_cny"],
        "collection_count": report["collection_count"],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
