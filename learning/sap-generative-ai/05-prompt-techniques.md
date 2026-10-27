# Analyzing Prompt Techniques

**Objective**

After completing this lesson, you will be able to analyze various prompt techniques such as one-shot, few-shot, and meta prompting.

## Analyzing Prompt Techniques

This lesson covers prompt techniques for obtaining accurate and context-specific responses from LLMs. By mastering methods like one-shot, few-shot, and meta prompting, you will acquire more granular control over the LLM's output, enabling you to build more robust and effective Generative AI features for your enterprise applications.

### One-Shot Prompting

One-shot prompting is the most straightforward technique. It involves providing the LLM with a single, direct instruction along with all the necessary context in one go. The model then generates a response based solely on this immediate input and its pre-trained knowledge. No examples of desired input-output behavior are provided within the prompt itself.

- **How it Works:** You simply state your request and include the relevant data. The LLM interprets the instruction and attempts to fulfill it.
- **When to Use It:** This technique is effective for well-defined, unambiguous tasks where the LLM's general understanding of language is sufficient to generate a satisfactory output. It's often used for:
  - Simple summarization (e.g., "Summarize this article.")
  - Basic question answering (e.g., "What is the capital of France?")
  - Straightforward classification (e.g., "Is this email positive or negative?")
- **Developer Context:** Ideal for initial prototyping or for tasks where data is already clean, and the desired output format is implicit or broadly understood. It's the baseline for many API calls.

#### Example:

- Summarize the following product description in one sentence:
- Product: SAP S/4HANA Cloud, Public Edition
- Description: SAP S/4HANA Cloud, Public Edition is a complete, ready-to-run cloud ERP solution with the latest industry’s best practices and continuous innovation. It helps businesses streamline core processes, gain real-time insights, and drive digital transformation.

**Expected Outcome:** A single-sentence summary of the provided text.

### Few-Shot Prompting: Learning from Examples

Few-shot prompting is a significantly more powerful technique that involves providing the LLM with a few (typically 1 to 5) examples of input-output pairs within the prompt itself. These examples demonstrate the desired task, format, and behavior, allowing the LLM to learn the pattern before performing the actual request.

- **How it Works:** You give the LLM a set of completed examples that show it what you want and how you want it. After these examples, you provide the actual new input for which you want a response. The LLM leverages the patterns demonstrated in the examples to generate its output for the final input.
- **When to Use It:** Few-shot prompting is incredibly effective for tasks that require:
  - **Specific Formatting:** When the output needs to adhere to a strict structure (e.g., JSON, XML, specific report template).
  - **Nuanced Interpretation:** When the task is domain-specific or requires the LLM to infer a subtle pattern or distinction that's hard to describe purely with words.
  - **Consistent Style or Tone:** To guide the LLM to write in a particular voice or adhere to brand guidelines.
  - **Custom Classifications:** When classifying text into categories not commonly known to the LLM (e.g., custom error codes, specific sentiment types for your product).
- **Developer Context:** This technique is invaluable when fine-tuning a model is not feasible due to cost or data availability, but you need higher accuracy and consistency than one-shot prompting can provide. It's a common strategy for improving model performance in enterprise applications without retraining.

#### Example:

Convert the following customer support questions into concise, internal-facing issue descriptions, maintaining the key problem:

Customer: "My app keeps crashing when I try to upload documents."

Internal Issue: App crashes during document upload.

Customer: "I can't log in to my account. It says, 'invalid credentials' but I'm sure my password is correct."

Internal Issue: User unable to log in due to invalid credentials error.

Customer: "The report I generated yesterday for Q3 sales is showing incorrect numbers for the Asia Pacific region. All other regions look fine."

**Expected Outcome:** The LLM completes the last "Internal Issue" based on the pattern established by the two examples.

### Meta Prompting

Meta prompting, often referred to as "system prompting" in many LLM APIs (like those used with SAP’s generative AI hub), involves providing an overarching instruction that defines the LLM's persona, its overall goal, its constraints, or the rules it should follow for an entire session or series of interactions. It sets the "stage" for all subsequent prompts.

- **How it Works:** This instruction typically comes before any specific user requests. It doesn't ask LLM to perform an immediate task, but rather to adopt a certain behavior or set of guidelines that will govern all its future responses within that interaction context.
- When to Use It: Meta prompting is powerful for:
  - **Establishing a Persona:** Making the LLM act as a specific expert or assistant (e.g., "You are an expert financial analyst.").
  - **Setting Guardrails:** Enforcing safety, ethical guidelines, or domain-specific rules (e.g., "Do not discuss politics," "Only provide answers based on the provided documents.").
  - **Defining Overall Intent:** Guiding the LLM's general approach to a conversation (e.g., "Your goal is to help users troubleshoot SAP security issues.").
  - **Ensuring Output Consistency Over Time:** Maintaining a consistent tone or style across multiple turns in a conversational application.
- **Developer Context:** Crucial for building conversational AI agents, internal knowledge assistants, or applications that require strict adherence to enterprise policies and data governance rules. It helps create a more controlled and predictable user experience.

#### Example (often sent as a "system" message in API calls):

You are an expert SAP Concur support agent. Your primary goal is to help users resolve issues related to expense report submissions. Always prioritize clear, actionable advice. Never provide financial advice or ask for sensitive personal information. If you cannot help, direct the user to the official Concur support portal.

#### Subsequent User Prompt:

I submitted my expense report for last month, but it's still showing as 'Pending Approval' after 5 days. What should I do?

**Expected Outcome:** The LLM's response will adhere to the persona and guidelines set in the meta prompt, focusing on actionable advice within Concur and avoiding financial recommendations.

**Combining Techniques:** It's important to note that these techniques are not mutually exclusive. For complex enterprise use cases, you will often combine them. For instance, you might use a meta prompt to define the LLM's role as a "technical documentation assistant" and then use few-shot examples within subsequent user prompts to specify the desired format for code snippets or API endpoint descriptions.

### Lesson Summary

This lesson introduces fundamental prompt engineering techniques, including One-Shot, Few-Shot, and Meta Prompting. These methods are intended to enhance control over LLM outputs, supporting the delivery of accurate and context-specific responses for enterprise applications. One-shot prompting leverages direct instructions for simple, well-defined tasks, while few-shot prompting significantly enhances accuracy and consistency by guiding the LLM with input-output examples, crucial for specific formatting or nuanced interpretations. Meta prompting, often used as system instructions, sets the LLM’s persona, constraints, and overarching guidelines for an entire interaction, establishing predictable and governed behavior. By mastering these methods, which can be effectively combined, you can build more robust and effective Generative AI features for your solutions within the SAP ecosystem.
