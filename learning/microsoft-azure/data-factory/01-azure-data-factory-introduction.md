# What is Azure Data Factory?

> **Source:** [What is Azure Data Factory? — Microsoft Learn](https://learn.microsoft.com/en-us/azure/data-factory/introduction) (article dated 2026-06-17, accessed 2026-11-05).
> Study summary. Terms follow Microsoft's official naming.

## Key idea

Azure Data Factory (ADF) is a **managed cloud data integration service** for complex hybrid **ETL** (extract, transform, load), **ELT** (extract, load, transform), and data integration projects. It lets you create and schedule data-driven workflows (**pipelines**) that move and transform data at scale.

The problem it solves: raw data is scattered across relational, non-relational, on-premises, and cloud systems, and on its own it lacks meaningful context. ADF orchestrates and operationalizes the processes that turn it into actionable business insight.

> **Note from the source:** *Data Factory in Microsoft Fabric* is the next generation of ADF (simpler architecture, built-in AI). Microsoft recommends starting with Fabric if you are new to data integration; existing ADF workloads can be upgraded to Fabric.

## Main features

| Feature | What it provides |
| --- | --- |
| Data compression | Compresses data during the Copy Data activity to optimize bandwidth. |
| Broad connectivity | Connectors for many different data sources and destinations. |
| Custom event triggers | Automatically runs an action when a specific event occurs. |
| Data preview and validation | Checks that data is copied and written correctly. |
| Customizable data flows | Lets you add custom actions or steps to data processing. |
| Integrated security | Microsoft Entra ID integration and role-based access control (RBAC). |

## Example scenario from the documentation

A gaming company produces petabytes of game logs in the cloud and wants to combine them with reference data (customers, games, marketing campaigns) stored **in an on-premises data store**. It needs to:

1. Join on-premises and cloud data.
2. Process it with Spark (Azure HDInsight).
3. Publish the results to a cloud data warehouse (Azure Synapse Analytics) for reporting.
4. Automate it on a **daily schedule** and also **when files arrive** in a Blob Storage container, with monitoring.

ADF is the platform that orchestrates that whole workflow.

## How does it work? The four stages

```
 Connect & collect ──► Transform & enrich ──► CI/CD & publish ──► Monitor
 (Copy activity)       (data flows / Spark,    (Azure DevOps, GitHub;  (Azure Monitor, API,
                        Databricks, HDInsight,  load into Synapse,      PowerShell, portal)
                        Machine Learning)       SQL, Cosmos DB…)
```

1. **Connect and collect:** connect to SaaS services, databases, file shares, FTP web services, etc., and move the data to a centralized store (for example Azure Data Lake Storage or Blob Storage) with the **Copy activity**. Without ADF you would have to build and maintain custom data movement services.
2. **Transform and enrich:** use **mapping data flows**, which run on Spark without you having to understand or manage Spark clusters; or, if you prefer hand-coded transformations, use external activities on HDInsight, Azure Databricks, or Machine Learning.
3. **CI/CD and publish:** full continuous integration and delivery support with Azure DevOps and GitHub. Refined data is loaded into Azure Synapse Analytics, Azure SQL Database, Azure Cosmos DB, or any analytics engine your BI tools can point to.
4. **Monitor:** track success and failure rates of scheduled activities and pipelines through Azure Monitor, API, PowerShell, Azure Monitor logs, and health panels in the Azure portal.

## Top-level concepts

An Azure subscription can contain one or more data factories. Key components:

| Concept | Short definition | Analogy |
| --- | --- | --- |
| **Pipeline** | Logical grouping of activities that performs a unit of work. Activities can run sequentially or in parallel. | The workflow / "program". |
| **Activity** | A single processing step. Three types: **data movement**, **data transformation**, and **control**. | A statement in the program. |
| **Dataset** | Data structure within a data store; points to the data an activity uses as input or output. | *What* data (table, folder, file). |
| **Linked service** | Connection information to an external resource, much like a connection string. Represents a **data store** or a **compute resource**. | *Where* and *how to connect*. |
| **Mapping data flow** | Visual, reusable transformation logic that ADF runs on a Spark cluster that spins up and down as needed. | Visual ETL without managing Spark. |
| **Integration runtime (IR)** | Compute environment where an activity runs or is dispatched from; the **bridge** between activity and linked service. Lets the activity run close to the data while meeting security and compliance needs. | The execution "engine". |
| **Trigger** | Determines **when** a pipeline run starts. Different trigger types exist for different events. | The scheduler / event. |
| **Pipeline run** | A specific instance of a pipeline execution, usually with arguments for its parameters (passed manually or by a trigger). | One run of the program. |
| **Parameters** | **Read-only** key-value pairs defined on the pipeline and consumed by its activities. Datasets and linked services are also strongly typed, reusable entities. | Input arguments. |
| **Control flow** | Orchestration of activities: chaining, branching, pipeline-level parameters, *ForEach* loops, etc. | `if`, `for`, sequencing. |
| **Variables** | Temporary values inside a pipeline; together with parameters they pass values between pipelines, data flows, and activities. | Local variables. |

### How the pieces fit together

```
Trigger ──starts──► Pipeline ──contains──► Activity (e.g. Copy)
                                              │          │
                                       input/output   runs on
                                              ▼          ▼
                                          Dataset   Integration runtime
                                              │
                                     uses the connection of
                                              ▼
                                       Linked service ──► Data store / compute
```

Rule of thumb: **the linked service defines the connection; the dataset defines the shape of the data.**
Example from the source: an Azure Storage linked service holds the connection string to the storage account; an Azure Blob dataset specifies the blob container and folder.

## Our addition: ADF and SAP

> Not part of the introduction article; added as context for this project. Verify against the [SAP connectors overview](https://learn.microsoft.com/en-us/azure/data-factory/industry-sap-overview).

- ADF provides connectors for SAP systems such as **SAP HANA**, **SAP Table**, **SAP BW Open Hub**, **SAP BW (MDX)**, **SAP ECC**, **SAP Cloud for Customer**, and **SAP CDC** (change data capture through the ODP framework).
- On-premises SAP systems usually require a **self-hosted integration runtime** installed inside the company network, along with the required SAP client components.
- Typical pattern: extract from SAP → land in Azure Data Lake Storage → transform (data flows / Databricks) → serve in Synapse or Fabric for BI.

## Review questions

1. What is the difference between ETL and ELT, and which does ADF support?
2. What is the difference between a linked service and a dataset?
3. What are the three types of activities?
4. What role does the integration runtime play, and why does it matter in hybrid scenarios?
5. What is a trigger, and how does it differ from a pipeline run?
6. Parameters vs. variables: which one is read-only?
7. What do mapping data flows run on, and what do you have to manage for that engine?
8. Which product does Microsoft recommend as the next generation of ADF?

<details>
<summary>Answers</summary>

1. ETL transforms before loading into the destination; ELT loads first and transforms in the destination. ADF supports both.
2. The linked service defines the connection (how to reach the resource); the dataset defines the structure or location of the data within that resource.
3. Data movement, data transformation, and control.
4. It provides the compute environment where the activity runs; it bridges activity and linked service and lets work run close to the data (including on-premises data) while meeting security and compliance requirements.
5. The trigger decides *when* a pipeline runs; the pipeline run is the resulting concrete instance.
6. Parameters are read-only; variables hold temporary values that can change.
7. On Spark clusters that ADF starts and stops as needed; you don't manage or maintain the clusters.
8. Data Factory in Microsoft Fabric.

</details>
