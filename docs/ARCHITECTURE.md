# Architecture

V0 is a local, file-based research environment: Python 3.12, uv, Polars/PyArrow, Parquet, DuckDB, and MLflow. Pandas is present only for ecosystem compatibility. PostgreSQL, Redis, schedulers, orchestration services, and production deployment are out of scope.

Gremlin owns acquisition, request/replay behavior, and source-level provenance. Quant Lab owns interpretation, validation, normalization, point-in-time features, experiments, models, and backtests. Quant Lab must not contain a financial website scraper.

`raw/` stores exact snapshot payload bytes addressed by checksum, plus a separate immutable provenance manifest for each capture. `bronze/` stores parsed source rows while preserving source fields and provenance. `silver/` stores normalized observations and explicit temporal columns. Bronze and silver files use the capture ID, so retrieving an unchanged payload later does not erase its new availability time. `features/` is reserved for point-in-time feature datasets. DuckDB is a disposable local query/catalog layer over Parquet; source data remains in files.
