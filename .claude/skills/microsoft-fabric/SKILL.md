---
name: microsoft-fabric
description: Design and build analytics on Microsoft Fabric with SAP data — choosing the SAP-to-Fabric ingestion path (ADF SAP CDC + OneLake shortcuts, Fabric Data Factory SAP connectors and copy jobs, Mirroring for SAP via SAP Datasphere, partner open mirroring), Fabric capacity, workspaces, lakehouses, medallion layout, Direct Lake for Power BI, security (workspace identity, trusted workspace access) and Fabric CI/CD.
---

# Microsoft Fabric for SAP analytics

Fabric is Microsoft's SaaS analytics platform: one **capacity** (compute you pay for), **workspaces** (containers with roles), and **OneLake** (one logical data lake in Delta/Parquet) shared by lakehouses, warehouses, Spark, pipelines and Power BI.
Fabric features move fast: confirm availability, preview status and limits with the `microsoft-learn` MCP server before recommending anything.

## 1. Choose the SAP → Fabric ingestion path

| Path | When it fits | Key requirements / caveats |
| --- | --- | --- |
| **A. ADF SAP CDC → ADLS Gen2 (Delta) → OneLake shortcut** | You already run Azure Data Factory (see `sap-cdc-incremental`), need ODP deltas (CDS views, extractors, SLT), want to keep data in your own storage account | Self-hosted IR; no data copy into OneLake — a shortcut in `Tables` exposes the Delta tables to SQL endpoint, Spark and Direct Lake |
| **B. Fabric Data Factory pipeline / copy job with SAP connectors** | Fabric-only estate; full or watermark-based loads | Connectors: SAP HANA, SAP Table, SAP BW Open Hub (application/message server). Uses the **on-premises data gateway** (not a self-hosted IR). "Copy job for SAP via ABAP Add-On" requires a Microsoft ABAP add-on installed in SAP |
| **C. Mirroring for SAP via SAP Datasphere** | Customer already licenses SAP Datasphere; wants near-zero-ETL continuous replication | Datasphere **Premium Outbound Integration** (SAP-billed); replication flow to ADLS Gen2 with *Group Delta = None*, *File type = Parquet*, load type *Initial and Delta* or *Initial Only*; then lakehouse shortcut + **Mirrored SAP** item. Fabric mirroring compute is free; storage free up to a capacity-based limit |
| **D. Partner solutions (open mirroring)** | Very large volumes, table-level deltas on ECC, special requirements | Third-party licensing; evaluate per partner |

Decision hints: existing ADF + ODP skills → **A**; SAP Datasphere already in place → **C**; simple full/watermark loads from HANA/BW → **B**. Always confirm SAP licensing for the chosen extraction method with SAP.

## 2. Platform setup

1. **Capacity** (Azure resource, F SKU) — `templates/bicep/fabric-capacity.bicep` + `templates/bicep/params/fabric-capacity.dev.bicepparam`. Deploy with the `azure-bicep-iac` skill (what-if first). Start with **F2** for dev; size production with the Fabric capacity estimator. Same region as the data.
   - Pause dev capacities when idle (billing stops): `az fabric capacity suspend --resource-group <rg> --capacity-name <name>` / `az fabric capacity resume ...`. Pausing makes content unavailable.
   - Pause/resume/scale needs only `Microsoft.Fabric/capacities/{read,write,suspend/action,resume/action}`: use a custom role, not Owner/Contributor.
2. **Tenant settings** (Fabric admin): enable *Service principals can use Fabric APIs* scoped to a security group for automation identities.
3. **Workspaces**: one per stage (dev/test/prod) and per team/domain, assigned to a capacity. Roles: Admin, Member, Contributor, Viewer — grant to groups.
4. **Workspace identity** (workspace settings → Workspace identity): lets shortcuts and pipelines reach ADLS Gen2 without secrets. Grant it *Storage Blob Data Reader* (shortcuts) or *Contributor* (pipelines writing) **at storage-account level**.
5. **Firewalled storage**: enable **trusted workspace access** on the storage account (resource instance rule for the workspace) instead of opening the firewall.

## 3. Lakehouse layout (medallion)

```
Lakehouse lh_sap_bronze   Files/  raw landings (if Fabric ingests directly)
Lakehouse lh_sap_silver   Tables/ shortcuts or Delta tables: cleaned SAP entities (sales order items, materials…)
Lakehouse lh_sap_gold     Tables/ business models: star schema for reporting
Semantic model (Direct Lake) ──► Power BI reports
```

- Put Delta **shortcuts in `Tables`** (one per table) so they appear in the SQL analytics endpoint; `Files` shortcuts are for raw files.
- Prefer **Direct Lake** semantic models on gold tables (no import refresh). With shortcuts, use **Direct Lake over OneLake** (or T-SQL in user identity mode) so the calling user's identity reaches the shortcut target.
- Keep SAP technical names in silver; translate to business names in gold.

## 4. Path A step by step (reuse the SAP CDC pipeline)

1. Run the `sap-cdc-incremental` pipeline so Delta tables land in `silver/sap/<entity>` in ADLS Gen2.
2. Create the workspace identity and grant it *Storage Blob Data Reader* on the storage account.
3. In Fabric, create a cloud connection to `https://<account>.dfs.core.windows.net` with **Workspace identity** authentication; copy its connection ID.
4. Create one shortcut per table with the REST API and `templates/fabric/shortcut-adls-delta.json` (see `templates/fabric/README.md`):

```bash
az rest --method post --resource https://api.fabric.microsoft.com --url "https://api.fabric.microsoft.com/v1/workspaces/<workspace-id>/items/<lakehouse-id>/shortcuts?shortcutConflictPolicy=CreateOrOverwrite" --body @templates/fabric/shortcut-adls-delta.json
```

5. Query through the SQL analytics endpoint; build gold tables with notebooks or SQL; create a Direct Lake semantic model.

## 5. Automation and CI/CD

- **Azure side** (capacity): Bicep (`azure-bicep-iac`).
- **Fabric side** (workspaces, lakehouses, shortcuts, items): Fabric REST API (`https://api.fabric.microsoft.com/v1/...`, token audience `https://api.fabric.microsoft.com`) or the **Fabric CLI** (`pip install ms-fabric-cli`, `fab auth login` — supports user, service principal and managed identity).
- **Lifecycle**: Fabric **Git integration** (workspace ↔ branch) plus **deployment pipelines** (dev → test → prod) or the **fabric-cicd** Python library from CI. Use **variable libraries** for stage-specific values (connections, paths). Create long-lived items (warehouses, lakehouses) with a **service principal**, not a personal account, so they keep working when people leave.

## 6. Checklist

- [ ] Ingestion path chosen and justified (A/B/C/D), SAP licensing confirmed.
- [ ] Capacity deployed via Bicep, sized, paused when idle (dev), least-privilege custom role for operators.
- [ ] Workspaces per stage, roles granted to groups.
- [ ] Workspace identity / trusted workspace access instead of keys or SAS.
- [ ] Delta shortcuts in `Tables`; medallion layers named consistently.
- [ ] Direct Lake semantic model on gold; row-level security if needed.
- [ ] Git integration + deployment pipeline (or fabric-cicd) set up; automation identity is a service principal.

## References (Microsoft Learn)

- Mirroring SAP (via SAP Datasphere): https://learn.microsoft.com/fabric/mirroring/sap
- Extract SAP data to Microsoft Fabric (options): https://learn.microsoft.com/azure/sap/workloads/extract-sap-data
- Fabric connector overview: https://learn.microsoft.com/fabric/data-factory/connector-overview
- OneLake shortcuts: https://learn.microsoft.com/fabric/onelake/onelake-shortcuts
- Create shortcut (REST): https://learn.microsoft.com/rest/api/fabric/core/onelake-shortcuts/create-shortcut
- Workspace identity: https://learn.microsoft.com/fabric/security/workspace-identity
- Trusted workspace access: https://learn.microsoft.com/fabric/security/security-trusted-workspace-access
- Pause and resume capacity: https://learn.microsoft.com/fabric/enterprise/pause-resume
- Fabric CI/CD best practices: https://learn.microsoft.com/fabric/cicd/best-practices-cicd
- Fabric CLI: https://learn.microsoft.com/rest/api/fabric/articles/fabric-command-line-interface
