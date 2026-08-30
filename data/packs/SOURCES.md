# Product-data source register

The CSV files under `data/packs/` are the public runtime data used by the
calculator. The documents used to review those values are kept locally under
`reference_documents/<country>/`, which is ignored by Git. The website does
not read those documents when it runs.

Before changing a CSV row, obtain the current manufacturer document from the
official source site, place it in the matching local folder, and verify every
changed value against the document. Record the document filename, page, and
review date in the CSV. Do not commit the document itself.

## Canada

| Public data | Source documents and official source site |
|---|---|
| `data/packs/canada/formulas.csv` | Abbott Nutrition Canada adult product information, available through [Abbott Nutrition](https://www.nutrition.abbott/ca/en/home.html); the current review references `2024_abbott-adult-product-guide.pdf`. |
| `data/packs/canada/formulas.csv` | Nestlé Health Science Canada product information, available through [Nestlé Health Science Canada](https://www.nestlehealthscience.ca/); the current review references `2026_nestle-product-guide.pdf`. |
| `data/packs/canada/formulas.csv` | Product-specific Abbott information sheets are recorded in the CSV by filename and page, including the Jevity, Osmolite, and TwoCal sheets. Keep current copies locally under `reference_documents/canada/`. |
| `data/packs/canada/formulas.csv`, `modulars.csv` | Canadian Medtrition/CMI Canada product panels, available through [CMI Canada](https://cmicanada.net/Medtrition/); keep the two-page product sheets locally under `reference_documents/canada/medtrition/`. |

The `source` column is the row-level map to the document and page. A source
site link is not evidence that a value is current; verify against the current
label or product information and update `verified` when the review is done.

## United States

`data/packs/usa/` is currently not a usable runtime data pack. US source
documents, when needed for future work, belong under
`reference_documents/usa/` and must not be used to populate Canadian rows.
The US manufacturer source site is [Medtrition](https://medtrition.com/).
Add a reviewed US CSV data pack and row-level source citations before
enabling US calculations.

## Local review workflow

For an update, tell the coding assistant the exact local folder and scope. For
example:

> Review the documents in `reference_documents/canada/` against the Canadian
> formula and modular CSVs. Show each changed value with its document and page,
> update only the CSV and `data/packs/SOURCES.md` when needed, and do not add
> or commit the source documents.

After reviewing the diff, run the data-loading tests and keep the source
documents in a private backup that follows the manufacturer's terms.
