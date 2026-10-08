"""Central configuration (env-driven)."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))
PORTAL_PORT = int(os.getenv("PORTAL_PORT", "8001"))
FINANCE_PORT = int(os.getenv("FINANCE_PORT", "8002"))
PORTAL_URL = f"http://127.0.0.1:{PORTAL_PORT}"
FINANCE_URL = f"http://127.0.0.1:{FINANCE_PORT}"

PORTAL_USER = os.getenv("PORTAL_USER", "ap.bot")
PORTAL_PASS = os.getenv("PORTAL_PASS", "portal123")

HEADLESS = os.getenv("HEADLESS", "1") != "0"
MAX_STEPS = int(os.getenv("MAX_STEPS", "40"))
APPROVAL_THRESHOLD = float(os.getenv("APPROVAL_THRESHOLD", "1000000"))
FLAKY_FINANCE = os.getenv("FLAKY_FINANCE", "1") != "0"

RUNS_DIR = ROOT / "runs"


def llm_provider() -> str:
    p = os.getenv("LLM_PROVIDER", "").strip().lower()
    if p:
        return p
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return ""
