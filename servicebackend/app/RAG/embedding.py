"""Shared DashScope embedding client and pgvector serialization helpers."""

from __future__ import annotations

import json
import math

from openai import OpenAI

from app.config.settings import settings


EMBEDDING_DIMENSION = 1024
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def embedding_client() -> OpenAI:
    if not settings.DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    return OpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        timeout=60.0,
        max_retries=2,
    )


def vector_literal(values: list[float]) -> str:
    """Encode a vector as pgvector text without an additional driver package."""
    if len(values) != EMBEDDING_DIMENSION or not all(math.isfinite(v) for v in values):
        raise ValueError(f"Expected {EMBEDDING_DIMENSION} finite embedding values")
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
