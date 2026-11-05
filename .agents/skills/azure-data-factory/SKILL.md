---
name: azure-data-factory
description: Design, build, deploy and troubleshoot Azure Data Factory (ADF) solutions — pipelines, activities, datasets, linked services, integration runtimes, triggers, parameters and mapping data flows. Use when the user wants to move or transform data with ADF or Data Factory in Microsoft Fabric.
---

# Azure Data Factory

Background notes: `learning/microsoft-azure/data-factory/01-azure-data-factory-introduction.md`.

## Core model (keep it straight)

- **Linked service** = the connection (where and how to connect). **Dataset** = the shape/location of the data inside it.
- **Activity** = one step (data movement, data transformation, or control). **Pipeline** = group of activities.
- **Integration runtime (IR)** = compute that runs the activity: *Azure IR* (cloud, serverless), *self-hosted IR* (on-premises / private networks), *Azure-SSIS IR* (lift-and-shift SSIS packages).
- **Trigger** decides when a pipeline runs: schedule, tumbling window, storage event, custom event.
- **Parameters** are read-only inputs; **variables** hold values that change during a run.

## Workflow

1. **Clarify requirements**: sources, sinks, volume, frequency, full vs. incremental load, transformations, SLA, network constraints (on-premises? private endpoints?).
2. **Decide ADF vs. Fabric Data Factory.** Microsoft positions Fabric Data Factory as the next generation; for new greenfield projects inside a Fabric tenant, consider it. Verify current feature parity with the `microsoft-learn` MCP server.
3. **Choose the integration runtime**: Azure IR for cloud-reachable sources; self-hosted IR for anything behind a firewall (including most SAP systems).
4. **Define linked services** with secrets in Key Vault (see `templates/adf/linked-services/`). Prefer managed identity for Azure targets.
5. **Define datasets** and **pipelines** (see `templates/adf/datasets/` and `templates/adf/pipelines/`). Parameterize table names, folder paths and dates instead of hardcoding.
6. **Incremental loads**: use a watermark column, change data capture (CDC) connectors, or tumbling window triggers.
7. **Deploy** the factory itself with Bicep (`templates/bicep/data-factory.bicep`) and the pipelines through Git integration + CI/CD (Azure DevOps or GitHub Actions), not by hand in production.
8. **Monitor**: configure diagnostic settings to Log Analytics and alerts on failed pipeline runs.

## Checklist before handing over

- [ ] No secrets in JSON or Bicep; Key Vault or managed identity used.
- [ ] Integration runtime documented (which machine, which network).
- [ ] Pipelines parameterized; no environment-specific values hardcoded.
- [ ] Retry policy and timeouts set on Copy activities.
- [ ] Failure alerting configured.
- [ ] Connector capabilities and limits verified on Microsoft Learn.

## Useful commands

```bash
az datafactory list --resource-group <resource-group> -o table
```

```bash
az datafactory pipeline create-run --factory-name <factory> --resource-group <resource-group> --name <pipeline>
```

(`az datafactory` requires the CLI extension: `az extension add --name datafactory`.)
