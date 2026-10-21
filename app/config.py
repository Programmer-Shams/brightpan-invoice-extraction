import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_SCHEMA = "invoice_extraction"
MODEL = os.getenv("EXTRACTION_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("EXTRACTION_EFFORT", "medium")
WORKER_THREADS = int(os.getenv("WORKER_THREADS", "2"))  # documents read in parallel
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.80"))
TOLERANCE = 0.02  # line math and totals must agree within two cents
API_TOKEN = os.getenv("API_TOKEN", "")  # every endpoint except /health requires "Authorization: Bearer <token>"
ALLOW_RESET = os.getenv("ALLOW_RESET", "0") == "1"  # POST /admin/reset deletes eval uploads only; dev/eval only
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3040")
N8N_OUTPUTS_WEBHOOK_URL = os.getenv("N8N_OUTPUTS_WEBHOOK_URL", "http://localhost:5679/webhook/brightpan-invoice-outputs")
OUTPUTS_WEBHOOK_SECRET = os.getenv("OUTPUTS_WEBHOOK_SECRET", "")
NOTIFY_EVAL = os.getenv("NOTIFY_EVAL", "0") == "1"

# USD per million tokens, Anthropic first-party rates (cached 2026-10-06 in the Claude API docs).
# Cache writes are priced at 1.25x input and cache reads at the listed rate (0.1x input where none is listed).
# Cost is computed from the token counts each response returns; unknown models report cost as null.
PRICING = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
}
