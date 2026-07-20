# HANDOFF.md — prompt to hand this project to another AI agent

> **What this is:** a paste-ready prompt for continuing work in **Cline**
> (VS Code) with **GLM-5.2** (`z-ai/glm-5.2` via OpenRouter), or any other
> agent. Rewritten 2026-07-19 after the Intake Record rework (a major
> architecture change — read Phase 1 below before assuming anything about
> "delivery schedules" or "the ingredient list" from an older mental model).
>
> **How to use it:** open Cline → paste the Phase 1 prompt below → replace
> the `[YOUR FEEDBACK HERE]` block with your actual testing notes. That's it.

---

> **2026-07-20 layout note:** the tab names referenced in older
> `CONTEXT.md` entries and in this file's open items ("Build" / "Intake"
> / "Results") are now **Nutrition Targets** / **Feed Recipes** /
> **Daily Intake Record** (see `CONTEXT.md` §9's 2026-07-20 entry), and
> the app is themed maroon via `.streamlit/config.toml`
> (`primaryColor #A4243A`, `secondaryBackgroundColor #f9e8eb` — theme
> changes require an app restart to take effect). Everything else in
> this prompt stands.

---

## Before you paste: two things

1. **Your feedback is the input.** These prompts are scaffolding; the
   value is in what *you* noticed using the app as an RD. Write your notes
   in plain clinical language — "the fluid numbers on the Results tab
   confused me" is more useful than a bug report. You don't need to know
   what's technically possible.
2. **Push before handing off** (`git push`). If a new agent misunderstands
   something, you want a clean remote to fall back to.

---

## PHASE 1 — Feed back your testing notes

Paste everything in this box:

---

I'm continuing work on the Blenderized Tube Feed Calculator, a Streamlit
app for registered dietitians. I'm the author — a dietitian (nutrition
subject-matter expert) learning Python. Explain jargon inline; don't dumb
down the clinical content.

**Orient yourself before touching anything:**

1. Read `CONTEXT.md` in full — especially **§9 (Current status)**, which is
   the single source of truth for what's done, and **§11 (Conventions &
   gotchas)**, which documents several traps that will bite you (a UTF-8
   BOM in some CNF CSVs, CNF's sodium row having the literal string `NA`
   in its Tagname which pandas silently reads as missing, and a Streamlit
   widget-state gotcha where `index=`/`value=` only take effect the first
   time a widget's `key=` is created).
2. Read `.clinerules` — the project's standing rules for AI agents.
3. Read `FEED_LOG_REWORK.md` in full — the design doc for the **Intake
   Record**, the app's current architecture for "what did the client
   actually receive." §6.2 explains why there is deliberately no
   over-draw/batch-mismatch flag; §2 explains the blend-vs-batch
   distinction. This is not optional background — most of the app's
   current data model is described here, not in BUSINESS_CASE.md.
4. Read `BUSINESS_CASE.md` **Appendix A** (every equation, documented) and
   **Appendix C** (the data-pack / nutrient-registry design). Appendix C is
   the architectural core for internationalization — understand it before
   proposing changes.

**Architecture you must not break:**

- **There is NO "over-draw" or batch-mismatch flag anywhere in this app,
  and none should be added.** Daily totals are a direct sum over Intake
  Record rows (`src/intake.py::aggregate_intake()`) — never a schedule
  volume extrapolated against a blend's measured batch volume. That
  extrapolation was a real, live bug (fixed 2026-07-19): the app used to
  silently assume a recipe's batch volume scaled to however much a
  delivery schedule claimed was given. The fix is: log what was actually
  given, as rows, and sum the rows. **If you find yourself writing
  anything that compares "volume logged" against "batch volume made" and
  flags a mismatch, stop — you are about to reintroduce the bug.** A
  blend's density is scale-free; logging the same blend more than once a
  day is normal use, not an anomaly.
- **Blend ≠ batch ≠ intake-record row.** A "blend" is a recipe formulation
  (ingredients + measured volume → densities via `calculate_profile()`).
  A "batch" is one physical making of a blend — the app does not track
  batches as a concept. An Intake Record row is what was actually given
  (time + source + amount), referencing a blend by id without caring how
  many times it was made. Keep these three separate in your head and in
  any code you write.
- **The Intake Record is ONE list, not two.** Rows have `source_type` ∈
  `{"blend", "formula", "flush", "oral"}` and display grouped under "Tube
  Feed" / "Food & Drink" headers, but they are backed by one
  `session_state["intake_log"]` list and one aggregation pass. Do not
  split this into two separately-maintained lists that get "combined" for
  a total — that recreates the dual-source-of-truth pattern that caused
  the original bug.
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
  re-scaffold, or re-test it unless a change genuinely requires it. If you
  need ingredient-scaling math outside a blend's density context (e.g. for
  a single oral food), use `src/calculator.py::compute_nutrient_totals()`
  — the extracted core `calculate_profile()` itself calls — never
  duplicate the grams×nutrient/100 merge-and-scale logic inline.
- **Never modify anything under `cnf_fcen_all-files-data_2026/`** (raw
  Health Canada data).

**How to verify — use these, never long inline `python -c` commands:**

```
.venv/bin/python scripts/verify_backend.py      # must print "=== ALL BACKEND MODULES VERIFIED ==="
.venv/bin/python scripts/check_app_imports.py   # must print "IMPORTS OK"
.venv/bin/python scripts/trace_calculation.py   # must print "CROSS-CHECK PASSED"
.venv/bin/streamlit run app/streamlit_app.py    # the app itself
```

`check_app_imports.py` alone does **not** prove a UI change works — it only
proves the module imports without error. For any UI change, write a
Streamlit `AppTest` script (`from streamlit.testing.v1 import AppTest`) that
drives the actual interaction and asserts on real output; recent commits in
this repo's history show the pattern. Report the actual AppTest output, not
a prose claim that something "works."

If you add backend features, **extend `scripts/verify_backend.py`** rather
than writing new one-off checks.

**My feedback from using the app:**

```
[YOUR FEEDBACK HERE — replace this whole block. Examples of useful notes:
 - "The X panel shows Y but I expected Z"
 - "I wanted to do A and couldn't find how"
 - "The number for B looked wrong when I did C"
 - "I never looked at D even once"
 - "Adding an oral food entry feels like too many steps"]
```

**How to work:**

1. **Plan before coding.** Show me what you intend to change and why,
   grouped by my feedback item. Flag anything where my request conflicts
   with the documented design (`BUSINESS_CASE.md`, `FEED_LOG_REWORK.md`) —
   I'd rather resolve the conflict than have it silently resolved for me.
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

- `thinning_liquids.csv` isn't pack-aware yet; `_load_thinning_liquids()`
  (`app/streamlit_app.py`) loads from a hardcoded `canada` path.
  `formulas.csv`/`_load_commercial_formulas()` (`src/calculator.py`) WAS
  fixed 2026-07-19 (now takes `pack: str = DEFAULT_PACK`). Documented in
  `CONTEXT.md` §9 and `BUSINESS_CASE.md` Appendix C. Inert until a second
  country pack exists.
- The commercial formula catalog grew from 8 to 33 adult Canadian
  tube-feeding formulas on 2026-07-19, gained a `brand` column and 9 more
  per-mL nutrient columns (fat/carbohydrate/fibre/sodium/potassium/
  calcium/iron/magnesium/phosphorus) — see `CONTEXT.md` §9's 2026-07-19
  entry for the full list of what changed and why. **None of it is
  clinically reviewed yet** — the author is doing that pass next. Don't
  treat it as validated, and don't redesign the Results tab comparator
  table without asking her first (she's flagged it as a design she's
  unhappy with but hasn't specified the fix for).
- Magnesium and phosphorus are deliberately target-less. Do not invent DRI
  targets for them — see `CONTEXT.md` §9 for the clinical reasoning.
- "Free water" in the Results tab blends two data sources into one number:
  CNF food moisture (blend/oral rows) and each commercial formula's
  declared `free_water_per_mL` (formula rows) — see
  `src/intake.py::IntakeTotals.free_water_mL`'s docstring. This is a
  deliberate design choice the author has not yet fully stress-tested
  against real mixed tube-feed-plus-formula days — treat feedback about it
  as high-signal, not a misunderstanding.
- "Add food/drink" uses an inline expander, not a popup dialog, because
  `st.dialog` is incompatible with the AppTest framework used to verify
  this app (any widget inside an open dialog becomes orphaned once it
  closes). If revisiting this UI, know that constraint before reaching for
  `st.dialog` again.
- "Recent/frequent foods" quick-add for oral entries (reduce repeat-logging
  friction) is a named future enhancement, not built — `FEED_LOG_REWORK.md`
  §4.
- Multi-day batch accounting (make Sunday, feed Mon–Wed, track what's
  left) is out of scope for the current model, which handles one day at a
  time — `FEED_LOG_REWORK.md` §4.
- Saving/loading blends or a day's Intake Record (JSON persistence) is not
  built — pairs naturally with this model but is its own task.

---

## PHASE 2 — Week 3 ("Build to Last")

Only start this once Phase 1 feedback is addressed and committed. Paste:

---

Continuing the Blenderized Tube Feed Calculator. Read `CONTEXT.md` (§9
status, §11 gotchas), `.clinerules`, `FEED_LOG_REWORK.md`, and
`BUSINESS_CASE.md` Appendix C first — same orientation rules and
verification commands as before; the nutrient registry
(`data/packs/canada/nutrients.csv`) is data, never hardcode a nutrient
list; there is no over-draw flag and none should be added (see Phase 1's
"Architecture you must not break" above — it applies here too).

This is **Week 3 — "Build to Last"** of a 4-week build plan
(`BUSINESS_CASE.md` §12). Scope, in priority order:

1. **pytest suite** (`tests/` exists but is empty — Phase 7 in the phase
   plan). Cover the real risk areas, not trivia:
   - `calculator.py`: the per-100g scaling (`compute_nutrient_totals()`),
     densities against a measured volume, dilution math,
     `label_to_per_100g`, custom-food folding.
   - `intake.py`: `aggregate_intake()` for each `source_type`; the
     original bug case (verify a single logged row never gets
     schedule-extrapolated); `InvalidBlendError` on a zero-volume blend;
     `sorted_intake_log()`'s unset-time-sorts-last behavior.
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
   GitHub. Requires the author's own Streamlit account connected to
   GitHub via share.streamlit.io — an AI agent cannot complete the
   account-linking step; scope your work to what's ready for that
   (confirm the app boots cleanly from a fresh clone, check whether
   `data/processed/*.parquet` — gitignored — is needed at runtime;
   `src/data_loader.py` prefers parquet and falls back to CSV, so confirm
   the CSV path works standalone, or build parquet at startup) and hand
   the actual deploy step back to the author.
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
| Adds an over-draw / batch-mismatch flag, or compares "logged volume" vs. "batch volume" | "Stop — read `FEED_LOG_REWORK.md` §6.2. That flag was deliberately removed; re-adding it reintroduces the original bug." |
| Extrapolates a schedule volume against a blend's measured volume (`density × schedule_volume` instead of summing Intake Record rows) | "That's the exact bug this app was reworked to fix. Totals must sum `intake_log` rows via `aggregate_intake()`, never extrapolate." |
| Splits the Intake Record into two separate lists | "One list, `intake_log` — read `FEED_LOG_REWORK.md` §2/§6.3 for why two lists recreates the original bug." |
| Hardcodes a nutrient list in Python | "That breaks the registry design — read `BUSINESS_CASE.md` Appendix C and use `data/packs/canada/nutrients.csv`." |
| Rewrites working backend modules | "The backend is verified per `CONTEXT.md` §9. Revert and make the minimal change." |
| Claims something works without showing output | "Show me the actual output of `scripts/verify_backend.py`, or the AppTest output for a UI change." |
| Invents clinical values (targets, formula numbers) | "Don't invent clinical numbers. Ask me — I'm the RD." |
| Makes a big change you didn't ask for | "Stop. Show me a plan first, grouped by my feedback items." |

**Your safety net:** every change is a git commit. `git log --oneline` shows
what happened; `git diff HEAD~1` shows the last change. Nothing is lost, and
almost anything can be undone — ask any agent to walk you through it.
