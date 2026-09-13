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

## Licence and attribution

Reviewed 2026-09-12. The same approach applies to formulas, modulars and ONS
in both calculators. [ISED's copyright guidance](https://ised-isde.canada.ca/site/ised/en/about-copyright)
distinguishes facts from their expression: individual nutrient facts are not
protected by copyright. An original selection or arrangement of data can be
protected as a compilation; see [CIPO's explanation](https://www.ised-isde.canada.ca/site/canadian-intellectual-property-office/en/copyright-learn-basics/copyright-learn-basics-protect-your-original-works-learn-why-copyright-matters).
Transcribing factual values does not, by itself, establish ownership of the
repository's compilation. The licence notice therefore makes no such ownership
claim and does not claim that the project relies on a blanket fair-dealing
exception.

[Abbott's Canadian terms](https://www.nutrition.abbott/ca/en/online-terms-and-conditions)
and [Nestlé's Canadian terms](https://www.nestlehealthscience.ca/en/info/terms-of-use)
address their source materials and trademarks separately from the factual
values used here. This repository uses product names for identification and
keeps the manufacturer source documents outside the public repository.

### Canadian Nutrient File

Source: Canadian Nutrient File, Health Canada, 2026. The bundled 2026 English
users' guide, page 45, permits commercial and non-commercial use without
further permission. It asks users to preserve source nutrient values (scaling
to other serving sizes is allowed), exercise care over accuracy, attribute
Health Canada and the edition, and avoid suggesting an official version,
affiliation or endorsement. CNF is provided without warranty as a reference
tool rather than individual medical advice.

The [official CNF page](https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/canadian-nutrient-file-about-us.html)
links to the [2026 dataset and guides](https://open.canada.ca/data/en/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109).
These are Health Canada's terms for CNF, not a grant under this project's MIT
licence. BTFCalc is not an official CNF version and is not affiliated with or
endorsed by Health Canada.
