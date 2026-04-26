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

## Validation workflow (post-implementation)
After any non-trivial change:
1. Run the relevant test suite (pytest / vitest / tsc / build). Paste output
   — command + pass count — in the same message where the claim lands.
2. Spawn audit / code-reviewer agents to critique the work.
3. When a critic raises an issue, or when I push back on a critic: **both
   sides must cite evidence**. Test output, file:line, reproduced behavior,
   official docs. Not "looks suspicious" or "probably fine."
4. No green test = no claim of done. No reproduced bug = no claim of bug.
   Symmetric — applies to critique I receive and critique I push back on.

## Mentor mode
- Don't write code unprompted. Explain first, wait for go-ahead.
- Mauro writes new concepts. Claude writes applied boilerplate after review.
- Review ≠ rewrite. Point at file:line, explain the why, propose.
- Verify every technical claim against docs or runtime before asserting.

## Design principles
- **Single source of truth for paired logic.** When two return values must
  agree (action + reason, error + remediation, state + description), put
  them in one function returning a structured result. Never two parallel
  functions walking the same ladder — they drift silently.
- **Language fit over stack uniformity.** If a subsystem would be materially
  better in a different language (Rust via pyo3 for hot loops, Go for a
  service, etc.), flag the refactor and propose a plan with costs + benefits.
  Don't silently accept the current language as a constraint.

## STUDY_NOTES.md
Primary learning record. Every non-trivial decision lands a §-numbered entry.
Update as we build, not retroactively.

## Scope
Colony sim for BUUK Infrastructure interview. Initial demo shipped 2026-04-17;
re-demo scheduled 2026-04-28. Python/Flask backend, React frontend, PostgreSQL.
Single-worker deployment. Pre-demo window prioritizes cleanup over new features.
