"""Event bus: the agent emits structured events; the dashboard polls them. Also brokers human replies."""
import threading
import time


class EventBus:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.pending = None
        self._answer = None
        self._evt = threading.Event()
        self.status = "running"

    def emit(self, type_: str, **data):
        with self.lock:
            e = {"id": len(self.events), "ts": time.time(), "type": type_, **data}
            self.events.append(e)
        return e

    def since(self, after: int):
        with self.lock:
            return self.events[after:]

    def ask(self, question: str, kind: str = "question", timeout: int = 900) -> str:
        """Block the agent until a human answers (kind: 'question' | 'approval')."""
        self._evt.clear()
        self.pending = {"question": question, "kind": kind}
        self.emit("approval_request" if kind == "approval" else "question", question=question)
        ok = self._evt.wait(timeout)
        self.pending = None
        if not ok:
            return "NO_RESPONSE (timed out waiting for a human)"
        ans = self._answer or ""
        self.emit("human_response", answer=ans)
        return ans

    def respond(self, answer: str) -> bool:
        if not self.pending:
            return False
        self._answer = answer
        self._evt.set()
        return True
