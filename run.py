"""Start the mock Invoice Portal, mock Finance App and the Agent Dashboard with one command."""
import subprocess
import sys
import time
import urllib.request
import uvicorn
import config


def wait_for(url: str, tries: int = 40):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    raise SystemExit(f"Service did not start: {url}")


def main():
    procs = []
    try:
        for mod, port in (("portal.app:app", config.PORTAL_PORT), ("finance.app:app", config.FINANCE_PORT)):
            procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", mod, "--port", str(port), "--log-level", "warning"],
                                          cwd=str(config.ROOT)))
        wait_for(f"{config.PORTAL_URL}/login")
        wait_for(f"{config.FINANCE_URL}/")
        print(f"\n  Invoice Portal : {config.PORTAL_URL}\n  Finance System : {config.FINANCE_URL}")
        print(f"  AGENT DASHBOARD: http://127.0.0.1:{config.DASHBOARD_PORT}   <- open this\n")
        if not config.llm_provider():
            print("  WARNING: no LLM key found. Copy .env.example to .env and set OPENAI_API_KEY or GEMINI_API_KEY.\n")
        uvicorn.run("dashboard.server:app", host="127.0.0.1", port=config.DASHBOARD_PORT, log_level="warning")
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
