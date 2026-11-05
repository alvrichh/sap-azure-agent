# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR**: a change that breaks existing users, such as renaming or removing a skill, changing template parameters in an incompatible way, or moving files that other agents or pipelines reference.
- **MINOR**: new skills, templates, test cases or capabilities that are backward compatible.
- **PATCH**: fixes and documentation that don't change behaviour for users.

Versions stay below `1.0.0` until at least one test case has passed end to end against real SAP and Azure systems. Until then, the templates are checked offline and in CI only.

## [Unreleased]

### Added

- Release workflow (`.github/workflows/release.yml`): pushing a tag `vX.Y.Z` publishes a GitHub Release with that version's changelog section (`scripts/release_notes.py`). Versions below 1.0.0 are marked as pre-releases.

## [0.7.0] - 2026-11-05

### Added

- CI compiles every Bicep template and parameter file with the linter (`scripts/build_bicep.sh`). Compiler type warnings, such as a property the API version doesn't know, fail the build.
- MIT license (`LICENSE`) and a license section in the README.
- This changelog, and `scripts/check_changelog.py`, which validates its format in CI.

### Changed

- GitHub Actions moved to Node 24 majors: `actions/checkout@v6`, `actions/setup-python@v6`, `actions/setup-node@v6`, `actions/setup-dotnet@v5`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`, `azure/login@v3` and `azure/powershell@v3`.

### Fixed

- `templates/bicep/eventhubs-graph-notifications.bicep` uses Event Hubs API `2024-01-01`. With API `2021-11-01`, `minimumTlsVersion` wasn't a valid property, so the TLS 1.2 minimum wouldn't have applied.

## [0.6.0] - 2026-11-05

### Added

- Test case `examples/powerplatform-sap`. A Power Apps app uses two Power Automate flows: `BAPI_MATERIAL_AVAILABILITY` through the SAP ERP connector and the on-premises data gateway, and business partners through the SAP OData connector via API Management with Entra ID.
- The test case keeps SAP connections per user and covers solution ALM: environment variables, connection references, deployment settings per environment, and GitHub Actions with pac CLI and OIDC.
- A small Workflow Definition Language evaluator, used by the unit tests to evaluate the flows' real expressions.
- Power Platform section in the `sap-api-integration` skill.

## [0.5.0] - 2026-11-05

### Added

- Test case `examples/adf-sap-to-snowflake`. Data Factory copies SAP tables (`KNA1`, `MARA`, `VBAK`) to ADLS as Parquet, then into Snowflake with a staged `COPY INTO` through a storage integration (no SAS). It reconciles row counts before running a `MERGE`.
- The test case uses key-pair authentication from Key Vault. Its SQL is generated from one object list, and the unit tests run the generated `MERGE` in DuckDB.
- Snowflake section in the `adf-sap-pipeline` skill.

## [0.4.0] - 2026-11-05

### Added

- Test case `examples/logicapps-sap-idoc`. It sends ORDERS05 IDocs to SAP with an explicit transaction ID (no duplicates on retry), provides an IDoc status API, and receives DEBMAS packets from SAP through a registered server program.
- `.env.example` with every non-secret setting (Azure, Microsoft 365, SAP hosts and URLs, Snowflake). `scripts/check_env_example.py` checks it in CI.
- Data Factory templates for Snowflake V2: key-pair linked service, staging storage with managed identity, dataset, and an ADLS-to-Snowflake pipeline.

### Changed

- `templates/bicep/logicapp-standard-sap.bicep` accepts VNet private ports (stateful mode for the SAP trigger and transaction IDs) and additional app settings.

## [0.3.0] - 2026-11-05

### Added

- End-to-end test cases, each with configuration, runbook, runtime test cases, a static validator and CI checks:
  - `examples/s4hana-to-fabric`: SAP CDC to Delta, with OneLake shortcuts in Fabric.
  - `examples/sap-odata-apim`: SAP OData behind API Management with Entra ID, using the SAP sandbox or your own S/4HANA.
  - `examples/graph-teams-approvals`: SAP purchase-order approvals in Teams, with Graph change notifications through Event Hubs.
  - `examples/logicapps-sap-rfc`: Logic Apps Standard calling SAP RFC/BAPI with the built-in connector.
- CI workflow `.github/workflows/validate.yml`.
- Overview diagram with line icons, and the CI badge in the README.

## [0.2.0] - 2026-11-05

### Added

- Agent skeleton: `AGENTS.md`, `CLAUDE.md`, the `azure-architect` and `sap-integration-expert` roles, and MCP configuration (`microsoft-learn`, `azure`) for Claude Code and OpenAI Codex.
- Skills: `azure-data-factory`, `adf-sap-pipeline`, `sap-cdc-incremental`, `adf-cicd`, `microsoft-fabric`, `sap-api-integration`, `microsoft-graph`, `azure-auth-entra` and `azure-bicep-iac`.
- Templates for Bicep, Data Factory, Fabric, API Management, Microsoft Graph and GitHub Actions.
- README, getting-started guide and templates index.
- Microsoft Azure learning notes (Azure Data Factory introduction).

### Changed

- All documentation translated to English.

## [0.1.0] - 2026-10-27

### Added

- Learning material: SAP large language model and generative AI lessons with an index.

[Unreleased]: https://github.com/alvrichh/sap-azure-agent/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/alvrichh/sap-azure-agent/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/alvrichh/sap-azure-agent/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/alvrichh/sap-azure-agent/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/alvrichh/sap-azure-agent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/alvrichh/sap-azure-agent/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alvrichh/sap-azure-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alvrichh/sap-azure-agent/releases/tag/v0.1.0
