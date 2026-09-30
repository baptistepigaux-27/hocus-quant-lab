# Quant Lab specifications

Implementation specs are intentionally separated from research philosophy.

- [SPEC-003 — Cross-sectional feature snapshot](003-cross-sectional-feature-snapshot/SPEC.md)
- [SPEC-004 — Historical feature cube](004-historical-feature-cube/SPEC.md)
- [SPEC-005 — Target Factory](005-target-factory/SPEC.md)

Reference design:

- [Quant Lab research philosophy](../docs/RESEARCH_PHILOSOPHY.md)
- [Target research philosophy](../docs/TARGET_RESEARCH_PHILOSOPHY.md)

Execution order:

1. build and freeze the cross-sectional feature contract;
2. apply it historically with SPEC-004;
3. construct independent future outcomes with SPEC-005;
4. only then test relationships between X and Y.
