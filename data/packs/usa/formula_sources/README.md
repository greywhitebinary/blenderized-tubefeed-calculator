# US product sheets — provenance notes, reference only

The US product documents used for future US work belong locally in
`reference_documents/usa/`. They are not included in the public repository.

**`data/packs/usa/` is NOT a usable data pack.** It holds archived source
documents and nothing else: no `nutrients.csv`, no `formulas.csv`, no
`modulars.csv`. Asking the app to load `usa` as a pack raises rather than
silently falling back to Canadian values, which is the behaviour
`src/calculator.py::_load_commercial_formulas()` exists to guarantee. The
directory is here so that country-specific material sits under the
country, and so a future US pack would find its sources already in place.

Nothing here may be cited in the `source` column of any pack's
`formulas.csv` or `modulars.csv`, and no number here may be copied into a
row that describes a Canadian product.

## Why the folder exists at all

Medtrition is a US company represented in Canada by CMI Canada, and the
Canadian range is both smaller and differently named. The Canadian sheets
live in `../../canada/formula_sources/medtrition/` and are the authority
for anything that ships.
These US guides serve two narrower purposes when they are available locally.

The first is corroboration. When a Canadian panel and its US counterpart
agree on serving size and macronutrients, that is evidence the two are the
same formulation under two names, which is worth knowing before trusting a
single undated sheet.

The second is that the US guides carry handling instructions the Canadian
sheets omit, in particular whether a supplement may be added to the enteral
formula itself. Those instructions are about the US product. Treat them as a
question to put to the manufacturer, not as an answer about the Canadian one.

## Name mapping

| US product | Canadian counterpart |
|---|---|
| Banatrol® Plus | BanatrAll with GOS |
| HyFiber® | HiFibre |
| ProSource® NoCarb Liquid Protein | ProSource® NoCarb Liquid Protein (same name) |
| Gelatein® Plus | listed by CMI Canada as coming soon; no Canadian sheet yet |

## Provenance

Retrieved 2026-08-28 from medtrition.com product pages, each file being the
"More Information" product guide linked from its own product page.
