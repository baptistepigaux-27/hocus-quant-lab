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

Notebook: [`model_lab.py`](../notebooks/model_lab.py). No fitting or portfolio replay
runs in the UI. Navigation includes Overview, Model Benchmark, Target Comparison,
Score Deciles, Backtest, Feature Importance and Methodology; all results are labelled
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
