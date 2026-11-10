"""Settings shared by the llm service launcher and the API-side client."""

from __future__ import annotations

import os

BASE_URL = os.environ.get("LLM_URL", "http://llm:8080")
MODEL_NAME = os.environ.get("LLM_MODEL", "qwen3-4b-instruct-2507-q4_k_m")
