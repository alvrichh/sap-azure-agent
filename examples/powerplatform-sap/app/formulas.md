# SAP Sales Assistant: canvas app formulas

Power Fx for the canvas app in the solution. Add both flows to the app (*Power Automate* pane); their names in Power Fx are the flow display names without spaces.

## Screen 1: material availability

| Control | Property | Formula |
| --- | --- | --- |
| `txtMaterial`, `txtPlant`, `txtUnit` | `Default` | `""` (`txtUnit`: `"ST"`) |
| `btnCheck` | `DisplayMode` | `If(IsBlank(txtMaterial.Text) Or Len(txtPlant.Text) <> 4, DisplayMode.Disabled, DisplayMode.Edit)` |
| `btnCheck` | `OnSelect` | `Set(varAvailability, 'SAP-Checkmaterialavailability'.Run(txtMaterial.Text, txtPlant.Text, txtUnit.Text))` |
| `lblQuantity` | `Text` | `If(varAvailability.status = "ok", "Available: " & varAvailability.quantity & " " & Upper(txtUnit.Text), varAvailability.message)` |
| `lblQuantity` | `Color` | `If(varAvailability.status = "ok", Color.DarkGreen, Color.DarkRed)` |

## Screen 2: business partners

| Control | Property | Formula |
| --- | --- | --- |
| `btnSearch` | `OnSelect` | `Set(varPartners, 'SAP-Searchbusinesspartners'.Run(txtName.Text)); ClearCollect(colPartners, ForAll(Table(ParseJSON(varPartners.partners)), {id: Text(ThisRecord.Value.id), name: Text(ThisRecord.Value.name), category: Text(ThisRecord.Value.category)}))` |
| `galPartners` | `Items` | `colPartners` |
| `lblSearchMessage` | `Text` | `If(varPartners.status = "error", varPartners.message, CountRows(colPartners) & " partners")` |

Notes:

- The flows always answer with `status`, a value and `message`, so the app never has to handle a failed flow call for business errors.
- Each user signs in to SAP with their own connection (both SAP connectors create non-shareable connections), so SAP checks the user's own authorizations.
