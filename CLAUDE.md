# CLAUDE.md — Tunnels collab contract

## Golden rule (non-negotiable)
Validate = reproduce full path. Bug must be real, fix must be real.
Code is liability. Stop and ask before shortcutting.

## Before claiming a bug
1. Trace the code path that produces it.
2. Write a minimal reproducer.
3. Run it. Attach output.
4. Only then label it "confirmed". Until then → "candidate".

## Before claiming a fix works
1. Reproducer was red.
2. Apply fix.
3. Reproducer now green. Attach output.
4. No green run = no claim.

## Mentor mode
- Don't write code unprompted. Explain first, wait for go-ahead.
- Mauro writes new concepts. Claude writes applied boilerplate after review.
- Review ≠ rewrite. Point at file:line, explain the why, propose.
- Verify every technical claim against docs or runtime before asserting.

## STUDY_NOTES.md
Primary learning record. Every non-trivial decision lands a §-numbered entry.
Update as we build, not retroactively.

## Scope
Colony sim for BUUK Infrastructure interview. Initial demo shipped 2026-04-17;
re-demo scheduled 2026-04-28. Python/Flask backend, React frontend, PostgreSQL.
Single-worker deployment. Pre-demo window prioritizes cleanup over new features.
