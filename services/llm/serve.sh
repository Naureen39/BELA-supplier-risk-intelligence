#!/bin/sh
# Start llama-server on the internal network only. No tools, no web access, bounded context.
# Requires a verified GGUF (see fetch_model.py).
set -eu
MODEL_FILE="${LLM_MODEL_FILE:-/models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf}"
exec llama-server \
  --model "$MODEL_FILE" \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 4096 --parallel 2 \
  --n-gpu-layers "${LLM_GPU_LAYERS:-99}" \
  --alias "${LLM_MODEL:-qwen3-4b-instruct-2507-q4_k_m}"
