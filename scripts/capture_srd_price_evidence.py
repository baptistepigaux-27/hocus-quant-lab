"""Cache public Euronext historical tables and issuer event releases for an audit.

Run with: uv run --with playwright python scripts/capture_srd_price_evidence.py
Uses the website's normal JavaScript AJAX conversion, without authentication.
Existing captures are preserved; request a different output root for a new vintage.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

EPISODES = [
    ("xfab", "BE0974310428", "2026-05-20", "2026-05-29"),
    ("maat-january", "FR0012634822", "2026-01-23", "2026-01-30"),
    ("maat-may", "FR0012634822", "2026-05-15", "2026-05-22"),
    ("nacon", "FR0013482791", "2026-02-13", "2026-03-05"),
    ("eramet", "FR0000131757", "2026-02-20", "2026-02-26"),
    ("ovh", "FR0014005HJ9", "2026-05-29", "2026-06-05"),
    ("stm", "NL0000226223", "2026-05-29", "2026-06-05"),
    ("guerbet", "FR0000032526", "2026-03-06", "2026-03-13"),
    ("valeo", "FR0013176526", "2026-05-29", "2026-06-05"),
    ("genfit", "FR0004163111", "2026-06-26", "2026-07-03"),
]
EVENTS = [
    (
        "nacon-suspension-issuer",
        "https://corporate.nacongaming.com/wp-content/uploads/2026/02/Nacon-CP-20.02.2026-Diffusion.pdf",
        "pdf",
    ),
    (
        "nacon-resumption-issuer",
        "https://corporate.nacongaming.com/wp-content/uploads/2026/03/Nacon-CP-03.03.2026-Diffusion.pdf",
        "pdf",
    ),
    (
        "maat-negative-issuer",
        "https://www.maatpharma.com/may-20-2026-maat-pharma-provides-an-update-on-the-application-for-marketing-authorization-of-maat013-xervyteg-in-the-treatment-of-acute-graft-versus-host-disease/",
        "html",
    ),
]


async def capture(root: Path, cases: Path | None = None) -> None:
    from playwright.async_api import async_playwright

    episodes = EPISODES
    nb_session = 30
    if cases is not None:
        import polars as pl

        groups = (
            pl.read_csv(cases, try_parse_dates=True)
            .filter(pl.col("primary_price_status") == "not_crosschecked")
            .group_by("isin")
            .agg(
                pl.col("entry_date").min().alias("start"),
                pl.coalesce("exit_date", "entry_date").max().alias("end"),
            )
            .sort("isin")
        )
        episodes = [
            (r["isin"], r["isin"], str(r["start"]), str(r["end"])) for r in groups.to_dicts()
        ]
        nb_session = 200
    root.mkdir(parents=True, exist_ok=True)
    if (root / "euronext_histories.json").exists():
        raise FileExistsError("Preserve existing evidence; choose another --output vintage")
    receipts = []
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            "https://live.euronext.com/en/product/equities/BE0974310428-XPAR",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_function("typeof jQuery !== 'undefined'", timeout=30000)
        for key, isin, start, end in episodes:
            params = {
                "startdate": start,
                "enddate": end,
                "adjusted": "0",
                "base100": "0",
                "nbSession": nb_session,
            }
            url = f"https://live.euronext.com/en/ajax/getHistoricalPricePopup/{isin}-XPAR"
            body = await page.evaluate(
                """args => new Promise((resolve, reject) => jQuery.ajax({
                type:'POST',url:args.url,data:args.params,
                success:data=>resolve(data),error:(x,s)=>reject(new Error(s))}))""",
                {"url": url, "params": params},
            )
            if not isinstance(body, str):
                raise ValueError(f"No public HTML response for {key}")
            table = await page.evaluate(
                """html => {
                const d=new DOMParser().parseFromString(html,'text/html');
                const t=d.querySelector('#AwlHistoricalPriceTable');
                return t?{headers:[...t.querySelectorAll('thead th')].map(x=>x.textContent.trim()),
                rows:[...t.querySelectorAll('tbody tr')].map(tr=>
                    [...tr.querySelectorAll('td')].map(x=>x.textContent.trim()))}:null
            }""",
                body,
            )
            if not table or not table["rows"]:
                raise ValueError(f"No prices in response for {key}")
            file = root / f"{key}.html"
            file.write_text(body)
            receipts.append(
                {
                    "episode": key,
                    "isin": isin,
                    "url": url,
                    "request_method": "POST",
                    "params": params,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "html_path": str(file),
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                    "table": table,
                    "access": "Public website UI AJAX, no login",
                }
            )
        await browser.close()
    (root / "euronext_histories.json").write_text(json.dumps(receipts, indent=2) + "\n")
    if cases is not None:
        return
    events = []
    for key, url, extension in EVENTS:
        with urlopen(url, timeout=30) as response:
            status, body = response.status, response.read()
        if status != 200 or not body:
            raise ValueError(f"Incomplete issuer response for {key}")
        file = root / f"{key}.{extension}"
        file.write_bytes(body)
        events.append(
            {
                "key": key,
                "url": url,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "http_status": status,
                "path": str(file),
                "sha256": hashlib.sha256(body).hexdigest(),
                "body_bytes": len(body),
            }
        )
    (root / "event_receipts.json").write_text(json.dumps(events, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("data/analysis/srd-price-audit-v1/primary")
    )
    parser.add_argument(
        "--cases", type=Path, help="Material case register to extend the first capture"
    )
    args = parser.parse_args()
    asyncio.run(capture(args.output, args.cases))
