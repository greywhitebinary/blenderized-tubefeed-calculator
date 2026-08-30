# Local source documents and private data

`reference_documents/` contains local-only manufacturer documents arranged by
country. It is ignored by Git and must never be added, committed, or pushed.
When updating public data-pack CSVs, read the relevant local document, report
each changed value with its document and page, and update the row-level source
and verification metadata. See `data/packs/SOURCES.md` for the public source
register.

`local_data/` is also ignored by Git. It may contain private alternative data
sets, which must not be used by, copied into, or assumed to be available to the
public deployment without the owner's explicit direction.
