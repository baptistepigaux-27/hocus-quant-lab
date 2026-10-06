# Quant Lab hosted services

## SPEC-008 Model Lab

The separate [Model Lab](https://sandbox.hocus.works/quant-model-lab/) is served by
`hocus-quant-model-lab-sandbox` on loopback port **8069**, from the isolated
`/home/ubuntu/worktrees/hocus-quant-spec008` worktree. It does not restart or modify
the SPEC-007 service on 8068. Existing sandbox authentication is inherited.

Templates: [`model-lab-sandbox.service`](../deploy/model-lab-sandbox.service) and
[`model-lab-nginx.conf`](../deploy/model-lab-nginx.conf). Replace `__ROOT__` in the
service template with the absolute checkout path. The service sees only its venv,
source/notebooks and precomputed SPEC-008 artefacts through read-only binds.

The full-registry experiment lives in `data/analysis/spec008-model-lab-all-features`,
with a second explicit read-only bind and `HOCUS_MODEL_LAB_ALL_DATA`. The experience
selector exposes both the original Strict/Strong run and the 1,048-feature run when
its completion summary is present. Neither run performs fitting in the UI.
The full-registry run also exposes a **Top 3 % / Top 10 %** portfolio selector after
the precomputed `portfolio-top03/summary.json` is present. Both choices read the same
models and scores. The nested replay is covered by the existing read-only data bind.
When `portfolio-top03/costs-25-45/summary.json` is present, the same bind also exposes
the **45 bp · mixte** scenario for all full-registry top3 models. This is a flat
round-trip cost assumption; it does not apply TTF per instrument.

The **Indices** tab reads `data/analysis/spec008-index-model-lab` through its own
read-only bind and `HOCUS_INDEX_MODEL_LAB_DATA`. It appears with performance tables
only after `index_report_complete.json` is present. Group (market/sector), target
and horizon controls are independent of the SRD selectors. Its baskets are mean
future-return diagnostics, with no trading backtest or transaction costs. See the
[index contract](SPEC_008_INDICES_CONTRACT.md) and
[generated index results](SPEC_008_INDICES_RESULTS.md). Generate data/run and then
execute `uv run python scripts/report_index_models.py` and
`uv run python scripts/audit_index_dataset.py --include-models` before deploying
this tab. Only a successful independent reconciliation writes the completion marker.

The **Grands marchés** tab reads `data/analysis/index-series-models-v1` via its own
read-only bind and `HOCUS_INDEX_SERIES_DATA`. It selects one of CAC40, SBF120,
S&P500, DAX40 and FTSE100, then direction/return/volatility and H5/H10. Every fitted
estimator uses only dates of that index. The publication marker `report_complete.json`
requires source/feature-prefix audits and checks of each estimator's single-index
metadata. Generate the artefacts with `scripts/index_series_models.py` actions
`prepare`, `run`, then `publish`; see the
[time-series contract](INDEX_SERIES_MODELS_CONTRACT.md).

The **SBF 120 · régimes** tab reads `data/analysis/sbf120-kmeans7-v1` through
`HOCUS_SBF120_REGIMES_DATA` and a separate read-only bind. Generate it with
`uv run python scripts/sbf120_kmeans.py` before installing the updated service
template. Its seven centres and outcome tables fit 2024 only; no UI fitting.
Date/target/horizon controls expose profiles, occupancy, distance to training
support, forecasts, individual block intervals and the assignment ledger.
See [the regime contract](SBF120_KMEANS7_CONTRACT.md).

Install a changed template and restart only the Model Lab service:

```bash
sed "s|__ROOT__|$(pwd)|g" deploy/model-lab-sandbox.service > /tmp/model-lab-sandbox.service
sudo install -m 0644 /tmp/model-lab-sandbox.service /etc/systemd/system/hocus-quant-model-lab-sandbox.service
sudo systemctl daemon-reload
sudo systemctl restart hocus-quant-model-lab-sandbox
```

The loopback endpoint is `http://127.0.0.1:8069/quant-model-lab/`. Nginx routing
and authentication are unchanged. Current deployment receipts and model replay
counts are recorded in [the execution journal](RESEARCH_PROGRESS_2026_10_06.md).

Notebook: [`model_lab.py`](../notebooks/model_lab.py). No fitting or portfolio replay
runs in the UI. Navigation includes Overview, Model Benchmark, Target Comparison,
Score Deciles, Backtest, Feature Importance, Methodology, Indices, Grands marchés
and SBF 120 · régimes;
all results are labelled
**development backtest — not independent confirmation**.

The local datasets/model files are not versioned. They must be generated with the
[documented CLI](SPEC_008_MULTIVARIATE_MODEL_BACKTEST.md) before starting this service.

## Existing research and confirmation services

The hosted notebook has separate staging and sandbox processes. Both run under
the dedicated `hocus-quant-lab` account with a read-only view of the project
virtualenv and local research data. Nginx keeps the existing host-specific
authentication and forwards each route to its own loopback port.

| Host route | Nginx upstream | Notebook | Purpose |
| --- | ---: | --- | --- |
| `/quant-lab/` on `staging.hocus.works` | `127.0.0.1:8066` | `/opt/hocus-quant-lab-staging/explorateur.py` | Archived Signal Atlas UI |
| `/quant-lab/` on `sandbox.hocus.works` | `127.0.0.1:8067` | `notebooks/explorateur.py` from the working repo | Stability Atlas preview |
| `/quant-lab-srd/` on `sandbox.hocus.works` | `127.0.0.1:8068` | `notebooks/srd_research_lab.py` | Interactive SRD 2024–2025 research lab |

The staging notebook is a read-only snapshot of the last committed explorer
before the SPEC-006R sandbox update. It can be refreshed independently. The
sandbox reads the generated atlas from `data/analysis/spec006r-stability-atlas`
and the existing signal database from `data/analysis/spec006-weekly-demo`.

Useful operations:

SPEC-006T adds **Research Contract**, **Candidate Explorer** and precomputed **Signal Detail**
to the SRD route. The ex-ante / future-clean toggle reads the local
`data/analysis/spec006t-ex-ante/` results; it does not run scans or bootstrap.
The immutable lock is also tracked at `configs/research/candidate_lock_v1.json`.
The SRD service mounts `src/` read-only to import the typed artifact loader.
Development periods 2025/2026 are explicitly labelled; independent confirmation is pending.

SPEC-007 adds **Confirmation Monitor** and a separate candidate confirmation detail.
Its local projections live in `data/analysis/spec007-confirmation/`. Initialize them with
`uv run python scripts/confirmation_spec007.py init` before restarting the service.
The service reads the frozen contract from the mounted data directory; it does not register,
advance, fit, or write confirmation results. All scientific collection uses the separate CLI.
The initial state is `awaiting_new_data`; there are no fabricated confirmation ICs.

```sh
sudo systemctl status hocus-quant-lab-staging hocus-quant-lab-sandbox
sudo systemctl status hocus-quant-lab-srd-sandbox
sudo journalctl -u hocus-quant-lab-sandbox -n 100 --no-pager
sudo nginx -t
```

Keep the Nginx snippets and systemd units separate when deploying later
notebook changes. Do not expose the source data directories through static
file serving; the notebook reads them through its service process.

The tracked deployment templates for the SRD lab are
`deploy/systemd/hocus-quant-lab-srd-sandbox.service` and
`deploy/nginx/quant-lab-srd-sandbox.conf`. The route inherits the sandbox
server's HTTP authentication. Its service opens DuckDB read-only and mounts the
virtualenv, data and notebooks read-only.

The HTTPS server block in `/etc/nginx/sites-available/sandbox.hocus.works.conf`
must retain both includes when regenerated or redeployed:

```nginx
include /etc/nginx/snippets/quant-lab-sandbox.conf;
include /etc/nginx/snippets/quant-lab-srd-sandbox.conf;
```

If the SRD include disappears, `/quant-lab-srd/` falls through to the site's
generic `/prototype/` redirect and returns 404. This occurred on 2026-10-03;
restoring the include and reloading Nginx restored the route. Verify the public
URL returns 401 without credentials, without a redirect to `/prototype/`, and
the loopback Marimo URL returns 200. Use a fresh query string if the browser has
cached the old permanent redirect.
