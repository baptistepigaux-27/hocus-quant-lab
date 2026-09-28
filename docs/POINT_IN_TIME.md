# Point-in-time data rules

Every observation keeps these concepts in separate columns:

- `observation_date`: period/date described by the source.
- `published_at`: when the source made the value public, if known.
- `retrieved_at`: when Gremlin captured the snapshot.
- `valid_from`: when this value/version is considered valid in the source's history, if known.
- `available_at`: conservative usability time, computed as the later of publication and retrieval when publication is known, otherwise retrieval time.

A point-in-time query must filter `available_at <= as_of`. Missing publication time does not imply early availability: retrieval time is the lower bound. Revisions are new observations/versions; they must not overwrite an earlier value that could have been known at an earlier cutoff. `valid_from` describes source validity and is not a substitute for publication or retrieval time.

For AMF, the consolidated CSV contains a publication **date** but no time. Gremlin retains that source date and leaves `published_at` null. Quant Lab accepts the row only from 00:00 UTC on the next calendar day (`publication_date + 1 day`); if publication date is absent, it requires `retrieved_at`. `position_date` never determines availability. This hides same-day rows even when queried later during the publication date.

Tests assert that every returned row is available by the requested cutoff and that rows retrieved after the cutoff are excluded even when their observation date is old.
