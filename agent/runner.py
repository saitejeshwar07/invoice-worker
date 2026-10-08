"""The agent runtime: plan -> act -> observe -> adapt -> verify -> complete."""
import json
import re
import time
import traceback
from pathlib import Path
import config
from agent import prompts
from agent.llm import LLM
from agent.tools import Blocked, BrowserSession, Policy, ToolError, tool_docs

WORKER_TOOLS = ["browser_goto", "browser_read_page", "browser_click", "browser_fill", "download_file",
                "read_pdf", "remember", "ask_human", "update_plan", "finish"]
VERIFIER_TOOLS = ["browser_goto", "browser_read_page", "browser_click", "browser_fill"]
BROWSER_ACTIONS = {"browser_goto", "browser_click", "browser_fill", "download_file"}


def render(template: str, tools: list[str]) -> str:
    return template.replace("{{CONTEXT}}", prompts.company_context()).replace("{{TOOLS}}", tool_docs(tools))


def compact(messages: list[dict], keep: int = 8, limit: int = 500) -> list[dict]:
    """Keep recent turns verbatim; shorten old observations (durable facts live in memory)."""
    n, out = len(messages), []
    for i, m in enumerate(messages):
        if i > 0 and i < n - keep and m["role"] == "user" and len(m["content"]) > limit:
            out.append({"role": "user", "content": m["content"][:limit] + " ...[truncated]"})
        else:
            out.append(m)
    return out


def verify(llm: LLM, session: BrowserSession, bus, task: str, claim: dict, memory: dict) -> dict:
    tb = session.toolbox("verify", policy=None, readonly=True)
    system = render(prompts.VERIFIER, VERIFIER_TOOLS)
    messages = [{"role": "user", "content": f"TASK GIVEN TO WORKER: {task}\n\nWORKER CLAIM: {json.dumps(claim)}\n\n"
                                            f"WORKER MEMORY (source data): {json.dumps(memory)}"}]
    for i in range(1, 11):
        d = llm.chat_json(system, compact(messages))
        tool, args = d.get("tool"), d.get("args") or {}
        messages.append({"role": "assistant", "content": json.dumps(d)})
        if tool == "verdict":
            return {"verified": bool(args.get("verified")), "checks": args.get("checks", []),
                    "summary": args.get("summary", "")}
        bus.emit("verify_action", step=i, tool=tool, args=args, thought=d.get("thought", ""))
        try:
            obs = tb.execute(tool, args) if tool in VERIFIER_TOOLS else f"ERROR: tool {tool} unavailable"
        except ToolError as e:
            obs = f"ERROR: {e}"
        if tool in BROWSER_ACTIONS:
            tb.screenshot(i, tool)
        messages.append({"role": "user", "content": f"OBSERVATION: {obs[:3000]}"})
    return {"verified": False, "checks": [], "summary": "Verifier ran out of steps without a verdict."}


def run_task(task: str, bus) -> None:
    run_dir = config.RUNS_DIR / bus.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    memory: dict = {}
    session = None
    final = None
    try:
        llm = LLM()
        bus.emit("start", task=task, provider=llm.provider, model=llm.model)

        # 1) Understand + plan (LLM-generated, not hard-coded)
        planner = render(prompts.PLANNER, WORKER_TOOLS)
        p = llm.chat_json(planner, [{"role": "user", "content": f"TASK: {task}"}])
        plan = [str(s) for s in p.get("plan", [])]
        bus.emit("plan", goal=p.get("goal", ""), plan=plan, missing_info=p.get("missing_info", []), revision=False)

        session = BrowserSession(run_dir, bus, headless=config.HEADLESS)
        policy = Policy(bus, config.APPROVAL_THRESHOLD)
        tb = session.toolbox("worker", policy)
        system = render(prompts.WORKER, WORKER_TOOLS)
        messages = [{"role": "user", "content": f"TASK: {task}\n\nINITIAL PLAN (revise with update_plan if needed):\n"
                                                + "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan))
                                                + (f"\n\nPLANNER FLAGGED MISSING INFO: {p.get('missing_info')}" if p.get("missing_info") else "")}]
        verify_attempts, consecutive_errors = 0, 0

        for step in range(1, config.MAX_STEPS + 1):
            d = llm.chat_json(system, compact(messages))
            tool, args = d.get("tool"), d.get("args") or {}
            messages.append({"role": "assistant", "content": json.dumps(d)})
            bus.emit("thought", step=step, text=d.get("thought", ""))
            bus.emit("action", step=step, tool=tool, args=args)
            obs, failed = "", False

            try:
                if tool == "finish":
                    status = str(args.get("status", "success")).lower()
                    claim = {"status": status, "summary": args.get("summary", ""), "evidence": args.get("evidence", [])}
                    if status == "success" and verify_attempts < 2:
                        verify_attempts += 1
                        bus.emit("verification_start", attempt=verify_attempts)
                        v = verify(llm, session, bus, task, claim, memory)
                        bus.emit("verification", **v)
                        if v["verified"]:
                            final = {**claim, "verified": True, "verification": v}
                            break
                        obs = ("VERIFIER REJECTED your completion claim: " + v["summary"] + " Checks: " + json.dumps(v["checks"])
                               + " Fix the problem or finish with status 'failed'.")
                        failed = True
                    else:
                        ok_unverified = status == "success"
                        final = {**claim, "status": "failed" if ok_unverified else status, "verified": False,
                                 "summary": claim["summary"] + (" [Not independently verified]" if ok_unverified else "")}
                        break
                elif tool == "remember":
                    memory[str(args["key"])] = args["value"]
                    bus.emit("memory", memory=dict(memory))
                    obs = f"Remembered {args['key']}."
                elif tool == "ask_human":
                    obs = "Human replied: " + bus.ask(str(args.get("question", "")))
                elif tool == "update_plan":
                    bus.emit("plan", goal="", plan=[str(s) for s in args.get("plan", [])], reason=args.get("reason", ""), revision=True)
                    obs = "Plan updated."
                elif tool in WORKER_TOOLS:
                    obs = tb.execute(tool, args)
                    if tool in BROWSER_ACTIONS:
                        tb.screenshot(step, tool)
                else:
                    raise ToolError(f"Unknown tool '{tool}'. Valid tools: {WORKER_TOOLS}")
            except Blocked as e:
                obs, failed = str(e), True
                bus.emit("blocked", step=step, error=str(e))
            except (ToolError, KeyError) as e:
                obs, failed = f"ERROR: {e}", True

            if failed:
                consecutive_errors += 1
                bus.emit("failure", step=step, tool=tool, error=obs[:400])
                if tool in BROWSER_ACTIONS:
                    tb.screenshot(step, tool)
            else:
                consecutive_errors = 0
                bus.emit("observation", step=step, tool=tool, text=obs[:1500])
                m = re.search(r"HTTP status: ([45]\d\d)", obs)
                if m:  # page-level error (validation / duplicate / 5xx): surface it, let the LLM decide how to adapt
                    snippet = obs.split("Page text:", 1)[-1].strip()[:200]
                    bus.emit("http_error", step=step, tool=tool, status=int(m.group(1)), error=snippet)
            if consecutive_errors >= 6:
                final = {"status": "failed", "summary": "Aborted after 6 consecutive failing actions.", "evidence": [], "verified": False}
                break
            messages.append({"role": "user", "content": f"OBSERVATION from {tool}: {obs[:3500]}\nMEMORY: {json.dumps(memory)}"})
        else:
            final = {"status": "failed", "summary": f"Step budget ({config.MAX_STEPS}) exhausted.", "evidence": [], "verified": False}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        final = {"status": "failed", "summary": f"Runtime error: {e}", "evidence": [], "verified": False}
    finally:
        if session:
            session.close()
    final["memory"] = memory
    bus.emit("final", **final)
    bus.status = "done"
    (run_dir / "log.json").write_text(json.dumps(bus.events, indent=2, default=str), encoding="utf-8")
