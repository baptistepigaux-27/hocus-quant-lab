# Quant Lab hosted services

The hosted notebook has separate staging and sandbox processes. Both run under
the dedicated `hocus-quant-lab` account with a read-only view of the project
virtualenv and local research data. Nginx keeps the existing host-specific
authentication and forwards each route to its own loopback port.

| Host route | Nginx upstream | Notebook | Purpose |
| --- | ---: | --- | --- |
| `/quant-lab/` on `staging.hocus.works` | `127.0.0.1:8066` | `/opt/hocus-quant-lab-staging/explorateur.py` | Archived Signal Atlas UI |
| `/quant-lab/` on `sandbox.hocus.works` | `127.0.0.1:8067` | `notebooks/explorateur.py` from the working repo | Stability Atlas preview |

The staging notebook is a read-only snapshot of the last committed explorer
before the SPEC-006R sandbox update. It can be refreshed independently. The
sandbox reads the generated atlas from `data/analysis/spec006r-stability-atlas`
and the existing signal database from `data/analysis/spec006-weekly-demo`.

Useful operations:

```sh
sudo systemctl status hocus-quant-lab-staging hocus-quant-lab-sandbox
sudo journalctl -u hocus-quant-lab-sandbox -n 100 --no-pager
sudo nginx -t
```

Keep the Nginx snippets and systemd units separate when deploying later
notebook changes. Do not expose the source data directories through static
file serving; the notebook reads them through its service process.
