"""Publish the correlation synthesis from frozen local analysis artefacts.

Usage: uv run --with weasyprint==66.0 python scripts/render_correlation_synthesis.py
Publication dependencies are transient; this does not run an analysis or acquire data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import markdown
import matplotlib
import numpy as np
import polars as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/EXPLORATION_CORRELATIONS_SYNTHESE.md"
MANIFEST = DOC.with_suffix(".sources.json")
FIGURES = ROOT / "docs/assets/correlations-exploration"
ANALYSIS = ROOT / "data/analysis"
WINDOWS = [3, 5, 10, 20, 30, 60, 120, 252]
NAVY = "#18354c"
TEAL = "#087e8b"
GOLD = "#ce8732"
GREY = "#c2ced6"


def verify_sources() -> None:
    """Fail explicitly if a source differs from the published provenance."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["sources"]:
        path = ROOT / entry["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"Source changed since synthesis: {entry['path']}")


def save_figure(fig: plt.Figure, name: str) -> None:
    fig.savefig(FIGURES / f"{name}.png", dpi=210, bbox_inches="tight", facecolor="white")
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def format_axes(ax: plt.Axes) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GREY)
    ax.grid(axis="y", color="#e5ebef", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(colors=NAVY, length=0, pad=8)


def build_figures() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    first = pl.read_csv(ANALYSIS / "spec006r-h5-top100-by-window/window_summary.csv")
    second = pl.read_csv(ANALYSIS / "spec006r-h5-top100-by-window-2025-2026/window_summary.csv")
    # Recompute counts from relation-level results, avoiding CSV name conventions.
    comparisons = pl.read_parquet(
        ANALYSIS / "spec006r-h5-top100-by-window-2025-2026/signal_comparison.parquet"
    )
    early, later = [], []
    for window in WINDOWS:
        row = first.filter(pl.col("feature_window") == window).row(0, named=True)
        early.append(row["inverted_pct"])
        cohort = comparisons.filter(pl.col("feature_window") == window)
        flips = cohort.filter(pl.col("ic_2025") * pl.col("ic_2026") < 0).height
        later.append(100 * flips / cohort.height)
    # The second published summary is also a required source, even though counts
    # above are calculated directly from its underlying comparisons.
    if second.filter(pl.col("feature_window").is_in(WINDOWS)).height != len(WINDOWS):
        raise ValueError("Incomplete 2025–2026 window summary")

    x = np.arange(len(WINDOWS))
    fig, ax = plt.subplots(figsize=(11, 5.5))
    format_axes(ax)
    for offset, values, color, label in [
        (-0.19, early, GOLD, "2024 → 2025"),
        (0.19, later, TEAL, "2025 → 2026 (partiel)"),
    ]:
        bars = ax.bar(x + offset, values, 0.35, color=color, label=label)
        ax.bar_label(bars, labels=[f"{v:.0f} %" for v in values], padding=4, fontsize=10)
    ax.set(xticks=x, xticklabels=WINDOWS, ylim=(0, 105))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    ax.set_xlabel("Fenêtre passée de la feature, en observations", labelpad=12)
    ax.set_ylabel("Part des IC moyens qui changent de signe")
    ax.set_title("Inversions du signe des corrélations", loc="left", color=NAVY, pad=34)
    ax.legend(loc="upper left", frameon=False, ncol=2)
    fig.text(
        0.13,
        -0.035,
        "100 variables sélectionnées sur 2024 par fenêtre · target direction H5",
        color=NAVY,
    )
    save_figure(fig, "inversions_par_fenetre")

    intervals = pl.read_parquet(ANALYSIS / "spec006r-h5-ic-confidence/window_summary.parquet")
    support_rows = [
        intervals.filter((pl.col("feature_window") == window) & (pl.col("block_length") == 4)).row(
            0, named=True
        )
        for window in WINDOWS
    ]
    series = [
        ([100 - value for value in later], GREY, "Même signe observé"),
        (
            [r["support_gt90_each_year_all_block_lengths"] for r in support_rows],
            GOLD,
            "Soutien annuel >90 %",
        ),
        (
            [r["joint_same_sign_support_gt90_all_block_lengths"] for r in support_rows],
            TEAL,
            "Soutien conjoint >90 %",
        ),
        (
            [r["ci90_excludes_zero_both_years_all_block_lengths"] for r in support_rows],
            NAVY,
            "Deux intervalles 90 % hors zéro",
        ),
    ]
    fig, ax = plt.subplots(figsize=(11, 6))
    format_axes(ax)
    for i, (values, color, label) in enumerate(series):
        bars = ax.bar(x + (i - 1.5) * 0.2, values, 0.18, color=color, label=label)
        ax.bar_label(bars, padding=3, fontsize=8)
    ax.set(xticks=x, xticklabels=WINDOWS, ylim=(0, 110))
    ax.set_xlabel("Fenêtre passée de la feature, en observations", labelpad=12)
    ax.set_ylabel("Variables sur 100, pour 2025 et 2026")
    ax.set_title("Du même signe observé aux critères d’incertitude", loc="left", color=NAVY, pad=42)
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=9)
    fig.text(
        0.13,
        -0.02,
        "Critères bootstrap exigés pour les blocs 2, 4 et 6 · intervalles individuels",
        color=NAVY,
    )
    save_figure(fig, "soutien_par_fenetre")

    examples = [
        ("open.level.q90_delta.w30.v1", "Écart Q90 du prix d’ouverture · W30"),
        ("ohlc.relation.close_open_return.w10.v1", "Rendement close/open moyen · W10"),
        ("close.log_return.q25.w252.v1", "Q25 des log-rendements · W252"),
        ("close.return.std.w252.v1", "Écart-type des rendements · W252"),
        ("ohlc.relation.candle_body.w120.v1", "Corps de bougie moyen · W120"),
    ]
    details = pl.read_parquet(ANALYSIS / "spec006r-h5-ic-confidence/sign_comparison.parquet")
    fig, ax = plt.subplots(figsize=(11, 6))
    format_axes(ax)
    for i, (feature_id, _) in enumerate(examples):
        row = details.filter(
            (pl.col("feature_id") == feature_id) & (pl.col("block_length") == 4)
        ).row(0, named=True)
        for year, offset, color in [(2025, -0.13, TEAL), (2026, 0.13, GOLD)]:
            mean = row[f"ic_{year}"]
            lower, upper = row[f"ci90_lower_{year}"], row[f"ci90_upper_{year}"]
            ax.errorbar(
                mean,
                i + offset,
                xerr=[[mean - lower], [upper - mean]],
                fmt="o",
                color=color,
                capsize=4,
                markersize=5,
                label=str(year) + (" (partiel)" if year == 2026 else "") if i == 0 else None,
            )
    ax.axvline(0, color=NAVY, linestyle="--", linewidth=1)
    ax.set(yticks=range(len(examples)), yticklabels=[e[1] for e in examples], xlim=(-0.09, 0.105))
    ax.invert_yaxis()
    ax.grid(axis="x", color="#e5ebef", linewidth=0.7)
    ax.set_xlabel("IC moyen de Spearman et intervalle bilatéral à 90 %", labelpad=12)
    ax.set_title("Exemples : amplitude et incertitude du signe", loc="left", color=NAVY, pad=50)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), frameon=False, ncol=2)
    fig.text(
        0.13,
        -0.035,
        "Target direction H5 · 10 000 réplications · blocs de 4 cutoffs · exemples exploratoires",
        color=NAVY,
    )
    save_figure(fig, "intervalles_exemples")


CSS = """
@page {
  size: A4; margin: 19mm 16mm 19mm 16mm;
  @top-left { content: 'HOCUS QUANT LAB · EXPLORATION DES CORRÉLATIONS';
    color: #617382; font: 7.5pt 'DejaVu Sans'; }
  @bottom-left { content: '5 octobre 2026 · résultats exploratoires';
    color: #617382; font: 8pt 'DejaVu Sans'; }
  @bottom-right { content: counter(page) ' / ' counter(pages);
    color: #18354c; font: 8pt 'DejaVu Sans'; }
}
body { color: #253a48; font: 10pt/1.45 'DejaVu Sans', sans-serif; }
h1 { font-size: 25pt; line-height: 1.2; color: #18354c;
     border-bottom: 3pt solid #087e8b; padding-bottom: 12pt; margin: 0 0 20pt; }
h2 { font-size: 16pt; color: #18354c; margin-top: 24pt; line-height: 1.25;
     break-after: avoid; }
h3 { font-size: 11.5pt; color: #087e8b; margin-top: 17pt; break-after: avoid; }
p { orphans: 3; widows: 3; margin: 8pt 0; }
a { color: #087e8b; text-decoration: none; overflow-wrap: anywhere; }
strong { color: #18354c; }
ul, ol { padding-left: 17pt; }
li { margin: 4pt 0; }
table { border-collapse: collapse; width: 100%; table-layout: fixed;
        font-size: 8pt; line-height: 1.35; margin: 12pt 0; }
thead { display: table-header-group; }
th { color: white; background: #18354c; text-align: left; font-weight: 600; }
td, th { padding: 6pt 5pt; border: 0.5pt solid #d5dfe5; overflow-wrap: anywhere; }
td { vertical-align: top; }
tr { break-inside: avoid; }
tr:nth-child(even) td { background: #f3f7f8; }
pre { background: #f3f7f8; border-left: 2pt solid #087e8b; padding: 10pt;
      font-size: 7.5pt; white-space: pre-wrap; overflow-wrap: anywhere; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 0.85em;
       overflow-wrap: anywhere; }
img { display: block; max-width: 100%; height: auto; }
p:has(img) { break-inside: avoid; break-after: avoid; margin: 14pt 0 3pt; }
p:has(img) + p { font-size: 8pt; color: #617382; break-before: avoid; }
blockquote { border-left: 2pt solid #ce8732; margin-left: 0; padding-left: 12pt; }
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-pdf", action="store_true", help="Generate only PNG/vector PDF figures"
    )
    parser.add_argument(
        "--output", type=Path, default=DOC.with_suffix(".pdf"), help="Output PDF path"
    )
    args = parser.parse_args()
    verify_sources()
    build_figures()
    if not args.no_pdf:
        from weasyprint import HTML

        source = DOC.read_text(encoding="utf-8").replace(
            "[Lire la version PDF](EXPLORATION_CORRELATIONS_SYNTHESE.pdf)\n", ""
        )
        body = markdown.markdown(source, extensions=["tables", "fenced_code"])
        html = (
            '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            "<title>Hocus Quant Lab — synthèse des corrélations</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html, base_url=str(DOC.parent)).write_pdf(args.output)
        print(f"PDF: {args.output}")
    print(f"Figures: {FIGURES}")


if __name__ == "__main__":
    main()
