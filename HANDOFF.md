# HANDOFF.md — prompt to hand this project to another AI agent

> **What this is:** a paste-ready prompt for continuing work in **Cline**
> (VS Code) with **GLM-5.2** (`z-ai/glm-5.2` via OpenRouter), or any other
> agent. Written 2026-07-16 so the author doesn't have to reconstruct
> context from memory.
>
> **How to use it:** open Cline → paste the Phase 1 prompt below → replace
> the `[YOUR FEEDBACK HERE]` block with your actual testing notes. That's it.

---

## Before you paste: two things

1. **Your feedback is the input.** These prompts are scaffolding; the
   value is in what *you* noticed using the app as an RD. Write your notes
   in plain clinical language — "the micro screen made me look for
   magnesium first, but it's buried" is more useful than a bug report. You
   don't need to know what's technically possible.
2. **Push before handing off** (`git push`). If a new agent misunderstands
   something, you want a clean remote to fall back to.

---

## PHASE 1 — Feed back your Week 2 testing notes

Paste everything in this box:

---

I'm continuing work on the Blenderized Tube Feed Calculator, a Streamlit
app for registered dietitians. I'm the author — a dietitian (nutrition
subject-matter expert) learning Python. Explain jargon inline; don't dumb
down the clinical content.

**Orient yourself before touching anything:**

1. Read `CONTEXT.md` in full — especially **§9 (Current status)**, which is
   the single source of truth for what's done, and **§11 (Conventions &
   gotchas)**, which documents two traps that will bite you (a UTF-8 BOM in
   some CNF CSVs, and CNF's sodium row having the literal string `NA` in its
   Tagname, which pandas silently reads as not-a-value).
2. Read `.clinerules` — the project's standing rules for AI agents.
3. Read `BUSINESS_CASE.md` **Appendix A** (every equation, documented) and
   **Appendix C** (the data-pack / nutrient-registry design). Appendix C is
   the architectural core — understand it before proposing changes.

**Architecture you must not break:**

- **The tracked-nutrient set is data, not code.** It lives in
  `data/packs/canada/nutrients.csv`, loaded by `src/nutrients.py`. Each
  nutrient has a `tier` (`label` = on Canada's mandatory Nutrition Facts
  panel → main adequacy table; `clinical` = tracked for a BTF-specific
  reason → collapsed micro screen; `engine` = internal only, e.g. water →
  never shown as a row) and `on_label` (whether a nutrition-facts label can
  supply it). **Never hardcode a nutrient list in Python.** The design
  rationale: a country's mandatory label panel *is* its public-health
  nutrient consensus, so the set must be per-country data.
- **The backend (`src/`) is complete and verified.** Don't rewrite,
  re-scaffold, or re-test it unless a change genuinely requires it.
- **Never modify anything under `cnf_fcen_all-files-data_2026/`** (raw
  Health Canada data).

**How to verify — use these, never long inline `python -c` commands:**

```
.venv/bin/python scripts/verify_backend.py      # must print "=== ALL BACKEND MODULES VERIFIED ==="
.venv/bin/python scripts/check_app_imports.py   # must print "IMPORTS OK"
.venv/bin/python scripts/trace_calculation.py   # must print "CROSS-CHECK PASSED"
.venv/bin/streamlit run app/streamlit_app.py    # the app itself
```

If you add backend features, **extend `scripts/verify_backend.py`** rather
than writing new one-off checks.

**My feedback from using the app on real recipes:**

```
[YOUR FEEDBACK HERE — replace this whole block. Examples of useful notes:
 - "The X panel shows Y but I expected Z"
 - "I wanted to do A and couldn't find how"
 - "The number for B looked wrong when I did C"
 - "I never looked at D even once"
 - "The order of the results doesn't match how I think about a recipe"]
```

**How to work:**

1. **Plan before coding.** Show me what you intend to change and why,
   grouped by my feedback item. Flag anything where my request conflicts
   with the documented design (`BUSINESS_CASE.md`) — I'd rather resolve the
   conflict than have it silently resolved for me.
2. **Ask me** if a piece of feedback is clinically ambiguous. I'm the domain
   expert; you're not. Don't guess at nutrition judgment.
3. **One change at a time.** After each: run all four verification commands
   above and report the results honestly. If something fails, say so with
   the output — don't paper over it.
4. **Commit after each meaningful change** (don't push). Update
   `CONTEXT.md` §9 when you're done, per `.clinerules` §6.
5. **Don't over-build.** If a fix is a one-line CSV edit, don't refactor a
   module.

**Known open items (context, not a to-do list — don't fix unasked):**

- `formulas.csv` and `thinning_liquids.csv` aren't pack-aware yet;
  `_load_commercial_formulas()` (`src/calculator.py`) and
  `_load_thinning_liquids()` (`app/streamlit_app.py`) load from a hardcoded
  `canada` path. Documented in `CONTEXT.md` §9 and `BUSINESS_CASE.md`
  Appendix C. Inert until a second country pack exists.
- The app implements a dilution *slider*; `BUSINESS_CASE.md` §7/A8 describes
  live recipe adjustment as the goal. Deferred UI rework, not a bug.
- Magnesium and phosphorus are deliberately target-less. Do not invent DRI
  targets for them — see `CONTEXT.md` §9 for the clinical reasoning.

---

## PHASE 2 — Week 3 ("Build to Last")

Only start this once Phase 1 feedback is addressed and committed. Paste:

---

Continuing the Blenderized Tube Feed Calculator. Read `CONTEXT.md` (§9
status, §11 gotchas), `.clinerules`, and `BUSINESS_CASE.md` Appendix C
first — same orientation rules and verification commands as before; the
nutrient registry (`data/packs/canada/nutrients.csv`) is data, never
hardcode a nutrient list.

This is **Week 3 — "Build to Last"** of a 4-week build plan
(`BUSINESS_CASE.md` §12). Scope, in priority order:

1. **pytest suite** (`tests/` exists but is empty — Phase 7 in the phase
   plan). Cover the real risk areas, not trivia:
   - `calculator.py`: the per-100g scaling, densities against a measured
     volume, dilution math, `label_to_per_100g`, custom-food folding.
   - `nutrients.py`: registry loads; `load_registry("no_such_pack")` raises
     `FileNotFoundError`; tier filters return the right sets.
   - `report.py`: `label` tier only in the main table; `clinical` tier only
     in the micro screen; `engine` tier never rendered; `target_type=UL`
     produces "Above UL"/"Below UL", not "Above target".
   - Use small fixture DataFrames — **do not** load the 565k-row CNF file
     in unit tests (that's what `verify_backend.py` is for).
2. **GitHub Actions CI** — run pytest + `ruff` + `black --check` on push.
   Don't run `verify_backend.py` in CI unless the CNF data is available to
   the runner; if it isn't, say so rather than silently skipping.
3. **Streamlit Community Cloud deploy** — free public URL, auto-deploy from
   GitHub. Check whether `data/processed/*.parquet` (gitignored) is needed
   at runtime; `src/data_loader.py` prefers parquet and falls back to CSV,
   so confirm the CSV path works on a fresh clone, or build parquet at
   startup.
4. **USDA SR Legacy supplement** (see `BUSINESS_CASE.md` §8) — CNF-first
   search, USDA fallback for foods CNF lacks. **Design it as a data pack
   concern**, consistent with Appendix C. Whole foods are interchangeable
   across databases; packaged foods are not. Propose the design and get my
   sign-off *before* implementing — this is the biggest change in Week 3.

Plan first, show me the plan, then implement one item at a time with
verification after each. Commit per item; don't push. Update `CONTEXT.md`
§9 as you go.

---

## If the agent goes off the rails

Signs to watch for, and what to say:

| Sign | Say this |
|---|---|
| Hardcodes a nutrient list in Python | "That breaks the registry design — read BUSINESS_CASE.md Appendix C and use `data/packs/canada/nutrients.csv`." |
| Rewrites working backend modules | "The backend is verified per CONTEXT.md §9. Revert and make the minimal change." |
| Claims something works without showing output | "Show me the actual output of `scripts/verify_backend.py`." |
| Invents clinical values (targets, formula numbers) | "Don't invent clinical numbers. Ask me — I'm the RD." |
| Makes a big change you didn't ask for | "Stop. Show me a plan first, grouped by my feedback items." |

**Your safety net:** every change is a git commit. `git log --oneline` shows
what happened; `git diff HEAD~1` shows the last change. Nothing is lost, and
almost anything can be undone — ask any agent to walk you through it.
