# sap-azure-agent

A master agent for **Microsoft Azure and SAP integration**, built for [Claude Code](https://code.claude.com). Clone it, open it with Claude Code, and use it to design, build and deploy solutions on Azure and connect them with SAP S/4HANA or any other service.

It also hosts the learning material (SAP generative AI, Microsoft Learn notes) the agent uses as its knowledge base.

**Start here:** [Getting started](docs/getting-started.md)

## Repository structure

| Path | Purpose |
| --- | --- |
| `CLAUDE.md` | Agent instructions, security rules and conventions. |
| `.claude/skills/` | Skills: `azure-data-factory`, `adf-sap-pipeline`, `sap-cdc-incremental`, `azure-auth-entra`, `azure-bicep-iac`, `microsoft-fabric`, `sap-api-integration`. |
| `.claude/agents/` | Subagents: `azure-architect`, `sap-integration-expert`. |
| `.mcp.json` | MCP servers: Microsoft Learn (docs) and Azure (resources). |
| `templates/` | Reusable Bicep and ADF JSON templates. |
| `learning/` | Study notes (knowledge base). |
| `docs/` | User guides. |

## Roadmap

- Skills: Microsoft Graph.
- Templates: CI/CD for Data Factory with GitHub Actions.

## Learning material

### SAP: Generative AI and LLMs

[Lesson index: LLM fundamentals, SAP strategy, and prompt engineering](learning/sap-approach-to-large-language-models.md)

- [Describing LLMs](learning/sap-generative-ai/01-describing-llms.md)
- [Describing SAP's Generative AI Strategy](learning/sap-generative-ai/02-sap-generative-ai-strategy.md)
- [Starting From Ideation to Productization](learning/sap-generative-ai/03-ideation-to-productization.md)
- [Explaining Fundamentals of Prompt Engineering](learning/sap-generative-ai/04-prompt-engineering-fundamentals.md)
- [Analyzing Prompt Techniques](learning/sap-generative-ai/05-prompt-techniques.md)
- [Leveraging System, User, and Assistant Roles for Better Prompts](learning/sap-generative-ai/06-system-user-assistant-roles.md)
- [Securing and Hardening Prompts](learning/sap-generative-ai/07-securing-and-hardening-prompts.md)
- [Exploring RAG and Grounding Use Cases](learning/sap-generative-ai/08-rag-and-grounding-use-cases.md)
- [Introducing Prompt Optimization](learning/sap-generative-ai/09-prompt-optimization.md)
- [Evaluating and Testing Your LLM Use Case](learning/sap-generative-ai/10-evaluating-and-testing-llm-use-case.md)

### Microsoft Azure

[Microsoft Azure and Microsoft Learn index](learning/microsoft-azure/README.md)

- [What is Azure Data Factory?](learning/microsoft-azure/data-factory/01-azure-data-factory-introduction.md)

## Content guidelines

All documentation in this repository is written in English.

Keep and organize the material provided by the user, along with the user's decisions and corrections. Keep provisional ideas marked as provisional, and separate sources from interpretations.

For the SAP lessons, use only the text provided by the user: ignore external links and do not search the internet for additional information.

For the Microsoft Azure section, public Microsoft Learn pages may be consulted. Cite the URL and the access date, and mark any additions of our own.
