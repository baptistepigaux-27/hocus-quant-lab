# ABC Bourse delivery: OHLCV archives and instrument labels

This note documents the manual ABC Bourse files delivered on 2026-09-29 and
the reproducible import path through Gremlin and Quant Lab. Acquisition remains
manual: neither repository signs into ABC Bourse or fetches its files.

## Input files

The delivery contains ten ZIP archives and one Excel reference workbook:

| Archive universe | Source rows | Session coverage |
| --- | ---: | --- |
| SRD, complete | 199,416 | 2022-09-29 → 2026-09-28 |
| US equities | 904,551 | 2022-09-29 → 2026-09-28 |
| German equities | 465,958 | 2022-09-29 → 2026-09-28 |
| FX and rates | 147,149 | 2022-09-29 → 2026-09-28 |
| Market indices | 90,268 | 2022-09-29 → 2026-09-28 |
| Cryptocurrencies | 75,363 | 2022-09-29 → 2026-09-28 |
| Sector indices | 29,998 | 2022-09-29 → 2026-09-28 |
| Commodities | 25,393 | 2022-09-29 → 2026-09-28 |
| Bonds | 6,350 | 2022-09-29 → 2026-09-28 |

The partial SRD archive contains 61,271 source rows, all in the full archive;
its overlapping monthly members were byte-identical. It is kept as raw
provenance and is not ingested a second time. The combined source total is
1,944,446 rows including full SRD. The current DuckDB views expose 1,940,462
distinct universe/identifier/session observations after collapsing 3,984
identical FX duplicates.

The bond inventory is consistent at 6,350 rows but omits two monthly members
that it declares to contain zero rows: `Cotations20250416.txt` and
`Cotations20250615.txt`. The per-archive audit records these omissions. No
conflicting duplicate OHLCV groups were found in the supplementary archives.

`Libelles_codes_perimetre_2022-2026.xlsx` records the source URL
`https://www.abcbourse.com/download/libelles` and a download date of
2026-09-29. Its summary covers 2,135 distinct codes, with 2,067 codes labeled,
68 lacking a current label, 2,122 label/ticker variants, and 55 codes with
multiple variants. The 68 missing labels are the SRD codes noted by the
workbook. Multiple names and tickers are preserved, not arbitrarily resolved.

## Import commands

Set `QUANT_INPUT_DIR` to the directory containing the delivered files. Keep the
archives and workbook outside Git; `data/` is ignored.

Set `QUANT_INPUT_DIR` to the delivery folder and extract the complete SRD ZIP
to a temporary directory. `TMP_SRD_DIR` must point to the extracted
`Cotations*.txt` files.

```sh
export QUANT_INPUT_DIR=/path/to/quant-delivery
TMP_SRD_DIR=$(mktemp -d)
unzip -q "$QUANT_INPUT_DIR/SRD_2022-09-29_2026-09-28.zip" -d "$TMP_SRD_DIR"

cd /path/to/hocus-gremlin
PYTHONPATH=src python3 -m gremlin.cli market-data import-abc-bourse \
  --input-dir "$TMP_SRD_DIR" \
  --artifact-root ./var/market-data/abc-bourse-full \
  --output ./var/market-data/abc-bourse-full/market-data.json
```

Then, from Quant Lab, ingest that Gremlin snapshot, the supplementary ZIPs,
and the label workbook:

```sh
cd /path/to/hocus-quant-lab
uv run python -m hocus_quant.cli ingest-market \
  /path/to/hocus-gremlin/var/market-data/abc-bourse-full/market-data.json \
  --gremlin-artifact-root /path/to/hocus-gremlin/var/market-data/abc-bourse-full
uv run python -m hocus_quant.cli ingest-market-archives "$QUANT_INPUT_DIR"
uv run python -m hocus_quant.cli ingest-instrument-labels \
  "$QUANT_INPUT_DIR/Libelles_codes_perimetre_2022-2026.xlsx"
```

The two archive commands are offline. Gremlin reads only the extracted SRD
files. Reimporting an unchanged data payload reuses its checksum-addressed raw
object while writing another capture record. Each Quant import writes a JSON
audit next to its silver data.

## Storage and query surfaces

- `data/raw/market/` and `data/raw/market_archives/` retain content-addressed
  Gremlin member payloads and original ZIPs, respectively.
- `data/raw/instrument_labels/` retains the original workbook and capture
  provenance.
- `data/bronze/market_daily/` and `data/silver/market_daily/` hold the SRD
  Gremlin handoff.
- `data/bronze/market_series/` and `data/silver/market_series/` hold the eight
  supplementary universes.
- `data/bronze/instrument_labels/` and `data/silver/instrument_labels/` hold
  normalized workbook rows, including unresolved codes and label variants.
- `data/silver/market_series/archive_audit.json` and the per-snapshot JSON
  files are generated audit outputs; they are not committed to Git.

DuckDB exposes `market_daily` / `market_daily_history` for SRD,
`market_series` / `market_series_history` for the additional universes,
`instrument_labels_history` / `instrument_labels_by_code` for reference data,
and the enriched `market_daily_with_labels` / `market_series_with_labels`
views. The marimo explorer reads this database in read-only mode.

## Identifier and point-in-time rules

The workbook's source column is named `ISIN`, but values such as `ABC000000087`
are ABC provider identifiers, not valid ISINs. Quant Lab joins metadata on the
unchanged `provider_instrument_id`; the ISIN field is populated only when the
identifier passes ISIN checksum validation. The dataset includes non-ISIN
codes, and label rows can contain multiple historical universe selections.

The supplementary market archives do not consistently specify currency or
MIC, so these fields remain null instead of being inferred from the ZIP name.
For these daily series, `available_at` is set to 00:00 Europe/Paris on the day
after the session. The workbook's labels are a current 2026-09-29 reference
snapshot, not point-in-time names or tickers; they must not be backdated in a
historical strategy without a dated reference history.

ABC Bourse notes that historical prices may be adjusted for nominal divisions.
The delivered files include no matching corporate-action history, so adjusted
price point-in-time safety is unverified. The import does not compute signals,
features, ranks, or model outputs.
