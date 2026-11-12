# CLAUDE.md

Project: AP Invoice Agent for the Zamp AI Solutions Analyst case study (PS-1).
Owner: Soumil. The full spec is in `PLAN.md`. Read it before any work.

## How we work

- Build exactly ONE layer from PLAN.md section 9 per session. Never start the next layer on your own.
- Start every layer by proposing a short plan (files to create, key decisions). Wait for approval.
- A layer is done only when its "Done when" check passes. Show the command output that proves it.
- After a layer passes: update the Status checklist in PLAN.md, then `git add -A && git commit -m "Layer N: <summary>"`.
- If the spec is ambiguous, make a sensible assumption, write it into `docs/assumptions.md`, and tell me. Ask only if it changes the decision logic.
- Ask before: installing a new dependency not in PLAN.md, changing the DB schema after Layer 3, any long or repetitive run.

## Usage and quota rules (important)

- Default `LLM_MODE=fixture`. Tests and dev loops never call Gemini.
- Only call real Gemini when I explicitly say so (recording fixtures, final checks).
- Keep responses and diffs focused. Don't rewrite files you don't need to touch.

## Architecture rules

- `backend/app/llm/gemini.py` is the only module that talks to an LLM.
- The LLM only extracts. All decisions come from deterministic rules in `pipeline/stages/`. No LLM calls in decide or explain.
- Every stage emits a StageEvent (RUNNING then PASS/WARN/FAIL/SKIPPED) with a payload the UI can render.
- Every rule returns a RuleResult with rule_id, outcome, severity, message, evidence. No silent checks.
- Money is always `Decimal`, never float. Display in ₹ with Indian digit grouping.
- Config only via env vars (`config.py`). Never hardcode the API key or model name.

## Code style

- Python: type hints everywhere, Pydantic models for all IO, small pure functions in stages, pytest.
- Frontend: TypeScript strict, functional components, Tailwind, one status color map shared everywhere (green approve, amber review, red reject).
- No em dashes in any user-facing text or docs.

## Commands

- Backend dev: `cd backend && uvicorn app.main:app --reload`
- Tests: `cd backend && pytest -q`
- Frontend dev: `cd frontend && npm run dev`
- Generate test data: `python scripts/generate_invoices.py && python scripts/seed_db.py`
