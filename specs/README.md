# Quant Lab specifications

Implementation specs are intentionally separated from research philosophy.

- [SPEC-003 — Cross-sectional feature snapshot](003-cross-sectional-feature-snapshot/SPEC.md)
- [SPEC-004 — Historical feature cube](004-historical-feature-cube/SPEC.md)

Reference design:

- [Quant Lab research philosophy](../docs/RESEARCH_PHILOSOPHY.md)

Execution order:

1. implement and validate SPEC-003 at the golden cutoff 2026-04-01;
2. freeze feature identities and formulas;
3. expand the same engine over time with SPEC-004;
4. only then introduce target / model / backtest specs.
