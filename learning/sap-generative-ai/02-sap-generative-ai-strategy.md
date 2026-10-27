# Describing SAP's Generative AI Strategy

**Objective**

After completing this lesson, you will be able to describe SAP's approach to large language models.

## Describing SAP's Generative AI Strategy

LLMs are powerful, however, they come with significant risks related to accuracy, data privacy, and bias. These risks must be systematically managed for these tools to be useful in a business context.

This lesson outlines SAP's strategy for doing just that. Instead of simply offering access to a generic LLM, SAP has developed a comprehensive framework to ensure that AI is applicable, dependable, and accountable for enterprise use cases. Understanding this approach is the first step toward building powerful and safe AI-driven applications within the SAP ecosystem.

#### SAP's Approach Towards LLMs

SAP's strategy for generative AI is not to compete with general-purpose models, but to harness their power by integrating them deeply and securely into business processes. This approach is built on three guiding principles: **Relevant, Reliable, and Responsible.**

### Relevant

**Relevant:** Grounding AI in Your Business Context

The primary limitation of a standard LLM is its lack of specific, real-time business knowledge. SAP addresses this through a concept called grounding. This means ensuring the LLM's response is based on factual, current data from your own enterprise systems, not just on its generic training data.

**How it Works:** Imagine a user asks an application, "What is the status of our top five sales orders?" Instead of letting the LLM guess, the application securely queries the real-time data from the SAP S/4HANA Cloud system. It then provides this factual data to the LLM and instructs it to "Summarize the status based on these facts."

This is where SAP's unique position becomes a key advantage. Because SAP applications are the system of record for the most critical business processes, ranging from finance to supply chain to human resources, the data used for grounding is unparalleled in its depth and quality. By building AI directly into these core processes, SAP ensures that the context provided to the LLM is not just random data but the very data that runs the business, making the output exceptionally **relevant.**

### Reliable

**Reliable:** Delivering Enterprise-Grade AI with the Generative AI Hub

Data privacy and security are non-negotiable in business. Using public LLMs directly exposes sensitive company data. SAP's strategy makes AI **reliable** by providing a secure, centralized platform to manage all generative AI interactions: the **generative AI hub** on the SAP Business Technology Platform (BTP).

**The Role of the Generative AI Hub:** The hub is a secure and reliable way to access leading models for your use cases. Instead of connecting directly to various external LLM providers, your application connects to a single, trusted entry point within your SAP environment.

The generative AI hub offers businesses a secure, centralized way to access multiple LLMs through a unified API, keeping company data private and protected. It ensures all generative AI interactions are governed, compliant, and fully auditable within the SAP environment.

For developers and data scientists, the generative AI hub is the primary tool for building enterprise-grade applications. It abstracts away the complexity and security risks, allowing you to focus on creating value.

### Responsible

**Responsible:** Committing to Ethical AI

AI must be fair and transparent to be truly enterprise-ready. Since LLMs can reflect the biases present in their training data, deploying them requires a commitment to ethical principles.

SAP's approach to **responsible** AI involves building safeguards into the platform and promoting best practices. This includes providing tools to test for bias, ensuring transparency when users are interacting with AI, and adhering to a strict AI ethics policy. This commitment aims to build solutions that are not only powerful but also trustworthy and fair.

### Lesson Summary

You can now describe SAP's strategic approach to generative AI. The key insight is that SAP focuses on the framework surrounding the LLM. By making AI **relevant** through grounding in critical business data, **reliable** through the secure **generative AI hub,** and **responsible** through a commitment to ethics, SAP provides the necessary foundation to move generative AI from a novelty into a core business tool. The generative AI hub is the central technology that enables this enterprise-ready strategy.
