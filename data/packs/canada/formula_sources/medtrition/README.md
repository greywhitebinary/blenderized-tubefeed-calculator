# Medtrition — Canadian provenance notes (CMI Canada)

The Canadian-labelled product sheets for the Medtrition products available
in Canada are the authority for the Medtrition rows in `../../formulas.csv`.
The source images are kept locally in
`reference_documents/canada/medtrition/` and are not required by the app.
The US guides are not Canadian sources and must never be cited in a `source`
column.

Medtrition, Inc. is represented in Canada by CMI Canada, whose Canadian
range is much smaller than the US catalogue and uses different product
names. Only what CMI Canada lists is in scope, on the author's call
(2026-08-28): the rest of the US catalogue is not something a Canadian
patient can obtain.

## Local files

Place the two-page sheets in `reference_documents/canada/medtrition/` using
the filenames listed below. The folder is ignored by Git, so these source
images remain available for local review without being published.

Each product is a two-page sheet. Page 1 is the product front, page 2
carries the bilingual Nutrition Facts / Valeur nutritive panel and the
directions for use, including tube feeding instructions where the sheet
gives them.

| Product | Files | Form | Panel basis |
|---|---|---|---|
| BanatrAll with GOS | `BanatrAll-with-GOS_CMI-Canada_p1.jpg`, `_p2.jpg` | powder | 1 package (11 g) |
| HiFibre | `HiFibre_CMI-Canada_p1.jpg`, `_p2.jpg` | liquid | 30 mL |
| ProSource NoCarb Liquid Protein | `ProSource-NoCarb_CMI-Canada_p1.jpg`, `_p2.jpg` | liquid | 30 mL |

Gelatein Plus is listed by CMI Canada as coming soon and has no Canadian
sheet, so it is not here.

## What these panels do and do not disclose

A Canadian Nutrition Facts table carries only the core set, so these sheets
give energy, fat, carbohydrate, fibre, sugars, protein, cholesterol, sodium,
potassium, calcium and iron, and nothing else. There are no vitamins and no
water content. Every other column in `formulas.csv` is therefore **blank**
for these products, per the blank-versus-zero rule in
`../UNIT_CONVERSIONS.md` section 8.

The US sheets do disclose a few figures the Canadian ones omit, phosphorus on
Banatrol Plus being the example. Do not borrow them. A row that mixes two
jurisdictions' documents is the failure mode `UNIT_CONVERSIONS.md` section 1
exists to prevent, only harder to spot.

## Provenance

Retrieved 2026-08-28 from cmicanada.net, from the product pages linked at
https://cmicanada.net/Medtrition/ . The nutrition panels are published as
images rather than text, so these are the page images as supplied.
