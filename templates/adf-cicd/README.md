# Data Factory CI/CD templates

| File | Copy to (in the repository connected to the **dev** factory) |
| --- | --- |
| `package.json` | `build/package.json` |
| `../github-actions/adf-cicd.yml` | `.github/workflows/adf-cicd.yml` |

Repository variables used by the workflow:

| Variable | Example |
| --- | --- |
| `ADF_ROOT_FOLDER` | `adf` (the *Root folder* set in the dev factory's Git configuration) |
| `DEV_FACTORY_ID` | `/subscriptions/<sub>/resourceGroups/rg-data-dev/providers/Microsoft.DataFactory/factories/adf-sapazdev` |
| `TEST_RESOURCE_GROUP`, `TEST_FACTORY_NAME` | `rg-data-test`, `adf-sapaztst` |
| `PROD_RESOURCE_GROUP`, `PROD_FACTORY_NAME` | `rg-data-prod`, `adf-sapazprd` |

Secrets (identifiers only, OIDC — no client secret): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. Create one identity per environment if test and prod must be isolated (`templates/bicep/github-oidc-identity.bicep`, subjects `repo:<org>/<repo>:environment:test` and `...:environment:production`).

Environment-specific values (linked service URLs, Key Vault names, integration runtime references) go in optional ARM parameter files `adf/cicd/test.parameters.json` and `adf/cicd/prod.parameters.json` (same format as the exported `ARMTemplateParametersForFactory.json`). Which properties become parameters is controlled by `arm-template-parameters-definition.json` in the ADF root folder (ADF Studio → Manage → ARM template → Edit parameter configuration).
