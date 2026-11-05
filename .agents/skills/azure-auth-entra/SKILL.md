---
name: azure-auth-entra
description: Design and configure identity and access with Microsoft Entra ID — managed identities, app registrations and service principals, workload identity federation (GitHub Actions, Kubernetes, other OIDC issuers), Azure RBAC, Key Vault access, and single sign-on / user provisioning / principal propagation between Microsoft Entra ID and SAP. Use whenever a solution needs something to authenticate to Azure, to Microsoft 365, or to SAP.
---

# Microsoft Entra ID: authentication and access

Goal: **no secrets to store or rotate** wherever the platform allows it, and **least privilege** everywhere. Verify details with the `microsoft-learn` MCP server before giving step-by-step instructions; Entra features and portal paths change often.

## 1. Pick the identity type

Ask: *who or what* needs access, *running where*, *to what*?

| Caller | Recommended identity | Secret to manage? |
| --- | --- | --- |
| Azure resource (Data Factory, Function, VM, App Service, Logic App…) → Azure resource | **Managed identity** | No |
| CI/CD (GitHub Actions, Azure DevOps), Kubernetes, another cloud → Azure | **Workload identity federation** on a user-assigned managed identity or an app registration | No |
| App or service outside Azure without OIDC support → Azure | App registration + **certificate** (client secret only as last resort) | Yes, store in Key Vault and rotate |
| Human users → Azure portal / resources | Entra user + group-based RBAC, MFA / Conditional Access | No |
| Human users → SAP applications | Entra SSO via **SAP Cloud Identity Services** (or direct SAML for SAP NetWeaver) | No |
| Azure / Microsoft 365 / Power Platform → SAP OData **as the signed-in user** | **SAP principal propagation** (typically through Azure API Management or SAP BTP) | No user secrets |
| Integration runtime → SAP via RFC (ADF SAP Table, SAP CDC, BW connectors) | SAP technical user; password in **Key Vault** | Yes (SAP side) |

### Managed identity: system-assigned vs. user-assigned

Microsoft's current guidance recommends **user-assigned** identities for most scenarios:

- **User-assigned**: lifecycle independent of the resource; can be shared by several resources; role assignments can be created *before* the resource exists; fewer role assignments to manage; avoids Entra object-creation throttling when deploying many resources.
- **System-assigned**: tied to one resource and deleted with it. Use it when you need audit logs to show the exact resource, or permissions must disappear with the resource.

Role assignments are **not** deleted automatically when an identity is deleted — clean them up.

## 2. Grant access with Azure RBAC

1. Choose the **narrowest built-in data-plane role** (e.g. *Storage Blob Data Reader/Contributor*, *Key Vault Secrets User*) instead of *Contributor* or *Owner*.
2. Assign at the **smallest scope** (resource > resource group > subscription).
3. Assign to **groups** for humans; directly to the identity for workloads.
4. Use Key Vault in **RBAC mode** (`enableRbacAuthorization: true`), not access policies.

```bash
az role assignment create --assignee-object-id <principal-id> --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope <resource-id>
```

Template: `templates/bicep/data-factory.bicep` shows managed identity + role assignments for Storage and Key Vault.

## 3. CI/CD without secrets: workload identity federation

For GitHub Actions deploying to Azure:

1. Create a **user-assigned managed identity** (or app registration) for the pipeline.
2. Add a **federated identity credential**:
   - issuer: `https://token.actions.githubusercontent.com`
   - audience: `api://AzureADTokenExchange`
   - subject must **exactly** match the workflow: `repo:<org>/<repo>:ref:refs/heads/main`, `repo:<org>/<repo>:environment:<name>`, or `repo:<org>/<repo>:pull_request`. Wildcards are not supported in the standard credential (flexible federated credentials, in preview, allow claim expressions).
3. Grant the identity RBAC on the target resource group only.
4. Store `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as GitHub secrets or variables (these are identifiers, not credentials).
5. In the workflow, set `permissions: id-token: write` and use `azure/login` with those IDs.

Templates:
- `templates/bicep/github-oidc-identity.bicep` — identity, federated credential and role assignment.
- `templates/github-actions/azure-login-oidc.yml` — workflow that logs in with OIDC and deploys Bicep.

CLI equivalent for an existing identity:

```bash
az identity federated-credential create --identity-name <identity> --resource-group <resource-group> --name github-main --issuer https://token.actions.githubusercontent.com --subject repo:<org>/<repo>:ref:refs/heads/main --audiences api://AzureADTokenExchange
```

## 4. Microsoft Entra ID and SAP

### Single sign-on and user provisioning

Recommended pattern (Microsoft and SAP joint guidance):

```
Microsoft Entra ID  ──SAML/OIDC + provisioning──►  SAP Cloud Identity Services  ──►  S/4HANA, BTP, SuccessFactors, Ariba…
 (leading IdP)                                      (proxy IdP + Identity Provisioning)
```

- Entra ID is the **corporate identity provider**; SAP Cloud Identity Services (Identity Authentication) acts as **proxy IdP** for SAP applications.
- Provision users (and groups mapped to SAP business roles) from Entra to SAP Cloud Identity Services, which provisions to S/4HANA (cloud, private edition or on-premises).
- Required Entra role to configure: Application Administrator, Cloud Application Administrator, or app owner.
- Classic SAP NetWeaver / on-premises ABAP systems can also integrate directly via SAML (Entra gallery app "SAP NetWeaver"); user mapping is maintained in SAP transaction `SAML2`.
- Start with a small pilot group and verify roles in SAP before rolling out.

### Principal propagation (acting as the user in SAP)

Needed when Power BI, Excel, Power Platform, Copilot Studio or a custom app must call SAP **with the end user's SAP authorizations** (not a shared technical user):

- **Azure API Management** exchanges the Entra token for an SAP-accepted token (SAML bearer / SAP OAuth 2.0 server on SAP Gateway) using an APIM policy; or
- **SAP BTP** (Integration Suite / API Management + Cloud Connector) performs the propagation.
- Each Entra user must map to a **named SAP user** (licensing implications: confirm with SAP).

### Data extraction (Data Factory → SAP)

RFC-based SAP connectors (SAP Table, SAP CDC, SAP BW Open Hub) authenticate with an **SAP user**, not Entra ID. Use a dedicated technical user with minimal authorizations, keep the password in Key Vault, and reference it from the linked service (`templates/adf/linked-services/sap-table.json`). Secure Network Communications (SNC) is recommended for encryption.

## 5. Checklist

- [ ] Every Azure-to-Azure connection uses a managed identity.
- [ ] CI/CD uses workload identity federation; no client secrets in GitHub.
- [ ] Remaining secrets (SAP passwords, third-party keys) live only in Key Vault, with an owner and a rotation plan.
- [ ] RBAC roles are data-plane, least privilege, at the smallest scope; humans get access through groups.
- [ ] Orphaned role assignments cleaned up.
- [ ] For SAP SSO: identity mapping attribute agreed (UPN / email / employee ID) with the SAP Basis team.
- [ ] Conditional Access / MFA applied to administrative access.

## References (Microsoft Learn)

- Managed identity best practice recommendations: https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations
- Workload identity federation — configure trust: https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust
- SSO with SAP Cloud Identity Services: https://learn.microsoft.com/entra/identity/saas-apps/sap-hana-cloud-platform-identity-authentication-tutorial
- User provisioning to SAP S/4HANA: https://learn.microsoft.com/entra/identity/saas-apps/sap-s4hana-provisioning-tutorial
- Securing access to SAP with Entra ID: https://learn.microsoft.com/entra/fundamentals/scenario-azure-first-sap-identity-integration
- SAP principal propagation for OData: https://learn.microsoft.com/azure/sap/workloads/expose-sap-odata-to-power-query
