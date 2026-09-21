"""Textbook-first retrieval and source-preserving web fallback for diagnosis."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.RAG.book_rag import search_textbooks
from app.agent.base import get_model
from app.agent.tools import search_web_sources


DOCTOR_BOOKS = ("diagnostics", "internal_medicine")
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _case_query(state: dict) -> str:
    summary = state.get("case_summary")
    if not summary:
        summary = next(
            (msg.content for msg in reversed(state.get("messages", []))
             if isinstance(msg, HumanMessage) and isinstance(msg.content, str)),
            "",
        )
    query = PHONE_PATTERN.sub("", str(summary))
    query = EMAIL_PATTERN.sub("", query)
    return query.strip()[:400]


def _rewrite_textbook_query(query: str) -> str:
    """One bounded retry; expand terminology without inventing case facts."""
    prompt = (
        "把病例描述改写为一条适合查《诊断学》《内科学》的中文检索问题。"
        "保留已经给出的部位、症状和时间；可加入医学同义词及‘鉴别诊断/相关检查’，"
        "不能添加用户没说过的症状、体征或确定疾病。只输出一行，不超过80字，"
        "不含姓名、电话或邮箱。"
    )
    response = get_model(enable_thinking=False).invoke([
        SystemMessage(content=prompt), HumanMessage(content=query)
    ])
    rewritten = response.content if isinstance(response.content, str) else ""
    rewritten = PHONE_PATTERN.sub("", rewritten)
    rewritten = EMAIL_PATTERN.sub("", rewritten)
    return rewritten.strip().strip("\"'“”")[:160]


def textbook_retriever_node(state: dict) -> dict:
    query = _case_query(state)
    if not query:
        return {
            "textbook_hits": [], "textbook_status": "no_match",
            "unavailable_books": [], "retrieval_queries": [],
        }

    queries = [query]
    try:
        result = search_textbooks(query, DOCTOR_BOOKS)
    except Exception as exc:
        print(f"教材检索失败: {exc}")
        return {
            "textbook_hits": [], "textbook_status": "error",
            "unavailable_books": [], "retrieval_queries": queries,
        }

    if not result.hits and len(result.unavailable_books) < len(DOCTOR_BOOKS):
        try:
            rewritten = _rewrite_textbook_query(query)
        except Exception as exc:
            print(f"教材问题改写失败: {exc}")
            rewritten = ""
        if not rewritten or rewritten == query:
            rewritten = f"{query} 症状 鉴别诊断 相关检查"[:160]
        queries.append(rewritten)
        try:
            result = search_textbooks(rewritten, DOCTOR_BOOKS)
        except Exception as exc:
            print(f"教材重试检索失败: {exc}")
            return {
                "textbook_hits": [], "textbook_status": "error",
                "unavailable_books": result.unavailable_books,
                "retrieval_queries": queries,
            }

    if result.hits:
        status = "partial" if result.unavailable_books else "ready"
    else:
        status = "unavailable" if len(result.unavailable_books) == len(DOCTOR_BOOKS) else "no_match"
    return {
        "textbook_hits": result.hits,
        "textbook_status": status,
        "unavailable_books": result.unavailable_books,
        "retrieval_queries": queries,
    }


def web_retriever_node(state: dict) -> dict:
    queries = state.get("retrieval_queries") or []
    query = queries[-1] if queries else _case_query(state)
    result = search_web_sources(query) if query else None
    return {
        "web_hits": result.hits if result else [],
        "web_status": result.status if result else "no_match",
    }
