"""Capture current ABC membership, verifying quote ISIN; no historical PIT claim.

Run with: uv run --with beautifulsoup4 python scripts/capture_srd_sector_mapping.py
"""

import hashlib
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path("data/analysis/srd-sector-action-v1")
RAW = ROOT / "raw_mapping"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(url, path):
    if not path.exists():
        for attempt in range(4):
            time.sleep(1.5)
            try:
                path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
                break
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 3:
                    raise
                time.sleep(max(1.0, float(error.headers.get("Retry-After", "1"))))
    return BeautifulSoup(path.read_bytes(), "html.parser")


def identity(soup):
    for script in soup.select('script[type="application/ld+json"]'):
        obj = json.loads(script.get_text())
        if isinstance(obj, dict) and obj.get("@type") == "Quotation":
            product = obj["itemOffered"]
            return product["identifier"][0]["value"], product["name"], obj["url"].rsplit("/", 1)[-1]
    return None, None, None


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    base = capture("https://www.abcbourse.com/marches/secteurs", RAW / "abc-sectors.html")
    industries = []
    memberships = {}
    member_names = {}
    inventory = pd.read_parquet("data/analysis/spec008-index-model-lab/universe_inventory.parquet")
    sector_codes = set(inventory.loc[inventory.research_group == "sector", "code"])
    for opt in base.select("#gpeco option[value]"):
        code = opt["value"]
        if not code:
            continue
        url = "https://www.abcbourse.com/marches/secteurs/" + code
        path = RAW / f"industry-{code}.html"
        soup = capture(url, path)
        index_ticker = soup.select_one("#shortid").get_text(strip=True)
        index_url = "https://www.abcbourse.com/cotation/" + index_ticker
        index_path = RAW / f"index-{index_ticker}.html"
        index_isin, index_name, _ = identity(capture(index_url, index_path))
        assert index_isin in sector_codes, (code, index_isin)
        rows = [
            {"ticker": a["href"].rsplit("/", 1)[-1], "name": a.get_text(" ", strip=True)}
            for a in soup.select('table a[href^="/cotation/"]')
        ]
        industries.append(
            {
                "industry_code": code,
                "industry_label": opt.get_text(),
                "sector_id": "abc-bourse-manual:index:" + index_isin,
                "sector_code": index_isin,
                "sector_name": index_name,
                "source_url": url,
                "source_path": str(path),
                "source_sha256": sha(path),
                "bridge_url": index_url,
                "bridge_path": str(index_path),
                "bridge_sha256": sha(index_path),
                "member_count": len(rows),
            }
        )
        for row in rows:
            member_names[row["ticker"]] = row["name"]
            memberships.setdefault(row["ticker"], []).append(industries[-1])
    universe = pd.read_parquet("data/analysis/srd-horizon-common-replay-v1/common_universe.parquet")
    entities = sorted(set(universe.loc[universe.in_common, "entity_id"]))
    with duckdb.connect("data/research.duckdb", read_only=True) as db:
        reference = db.execute("SELECT * FROM instrument_labels_by_code").df()
    reference.to_parquet(ROOT / "current_instrument_reference.parquet", index=False)
    reference_tickers = reference.set_index("provider_instrument_id").ticker.to_dict()
    retrieved = datetime.now(UTC).isoformat()

    def one(entity):
        isin = entity.rsplit(":", 1)[-1]
        url = "https://www.abcbourse.com/cotation/" + isin
        path = RAW / f"quote-{isin}.html"
        error = None
        try:
            actual, name, ticker = identity(capture(url, path))
        except Exception as exc:
            actual, name, ticker = None, None, None
            error = str(exc)
        possible = memberships.get(ticker, []) if actual == isin else []
        method = "quote_canonical_listing"
        if not possible and actual == isin:
            ref = reference_tickers.get(isin)
            candidate = ref + "p" if isinstance(ref, str) else None
            if candidate in memberships:
                alternate_url = "https://www.abcbourse.com/cotation/" + candidate
                alternate_path = RAW / f"quote-alternate-{isin}.html"
                try:
                    alternate_isin, _, _ = identity(capture(alternate_url, alternate_path))
                    if alternate_isin == isin:
                        possible = memberships[candidate]
                        method = "same_ISIN_Paris_listing_verified"
                except Exception:
                    pass
        if not possible and actual == isin and isinstance(name, str):
            plain = name.casefold()
            for suffix in [" nv", " sa", " se", " plc", " group se"]:
                plain = plain.removesuffix(suffix)
            candidates = [t for t, n in member_names.items() if n.casefold() == plain]
            for candidate in candidates:
                alternate_url = "https://www.abcbourse.com/cotation/" + candidate
                alternate_path = RAW / f"quote-alternate-{isin}.html"
                try:
                    alternate_isin, _, _ = identity(capture(alternate_url, alternate_path))
                    if alternate_isin == isin:
                        possible = memberships[candidate]
                        method = "same_ISIN_Paris_listing_verified"
                        break
                except Exception:
                    pass
        match = possible[0] if len(possible) == 1 else None
        return {
            "action_id": entity,
            "ISIN": isin,
            "instrument": name,
            "sector_id": match["sector_id"] if match else None,
            "industry_code": match["industry_code"] if match else None,
            "sector_name": match["sector_name"] if match else None,
            "mapping_match_method": method,
            "mapping_status": "current_snapshot_match" if match else "unmapped",
            "missing_reason": None
            if match
            else (
                "ambiguous_membership"
                if len(possible) > 1
                else "quote_isin_mismatch_or_unavailable"
                if actual != isin
                else "not_in_current_industry_membership"
            ),
            "current_ticker": ticker,
            "quote_identity_isin": actual,
            "source_url": match["source_url"] if match else None,
            "quote_url": url,
            "quote_path": str(path),
            "quote_sha256": sha(path) if path.exists() else None,
            "mapping_observed_at": retrieved,
            "historical_pit": False,
            "historical_changes_documented": False,
            "capture_error": error,
        }

    with ThreadPoolExecutor(max_workers=1) as pool:
        rows = list(pool.map(one, entities))
    pd.DataFrame(rows).to_parquet(ROOT / "action_sector_mapping.parquet", index=False)
    pd.DataFrame(rows).to_csv(ROOT / "action_sector_mapping.csv", index=False)
    (ROOT / "industry_bridge.json").write_text(
        json.dumps(industries, indent=2, ensure_ascii=False) + "\n"
    )
    manifest = {
        "observed_at": retrieved,
        "grade": "current snapshot projected on past cutoffs, not PIT",
        "source": "ABC ICB industry membership; ISIN-verified quote links",
        "reference_sha256": sha(ROOT / "current_instrument_reference.parquet"),
        "mapping_sha256": sha(ROOT / "action_sector_mapping.parquet"),
        "bridge_sha256": sha(ROOT / "industry_bridge.json"),
        "mapped": sum(r["sector_id"] is not None for r in rows),
        "actions": len(rows),
        "taxonomy": "11 CAC industries already in the frozen sector corpus",
        "raw_sha256": {str(p): sha(p) for p in RAW.glob("*.html")},
    }
    (ROOT / "mapping_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print({k: v for k, v in manifest.items() if k != "raw_sha256"}, flush=True)
    print(
        "Unmapped",
        [(r["ISIN"], r["instrument"], r["missing_reason"]) for r in rows if not r["sector_id"]],
        flush=True,
    )


if __name__ == "__main__":
    main()
