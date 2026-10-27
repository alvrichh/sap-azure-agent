# Leveraging System, User, and Assistant Roles for Better Prompts

**Objective**

After completing this lesson, you will be able to identify how the roles of System, User, and Assistant make prompts more effective.

## Leveraging System, User, and Assistant Roles for Better Prompts

Now, we'll dive into how modern LLM APIs, including those accessible via SAP’s generative AI hub, formalize this concept using distinct conversational roles: system, user, and assistant.

These roles are not just arbitrary labels; they represent a structured way for you to communicate with intent, provide context, and manage multi-turn interactions with an LLM. Enterprise application developers must understand and use these roles to deliver robust and context-aware AI solutions. This lesson will show you how these roles work together to make your prompts clearer and significantly more effective.

### Significance of Structured Roles

While a single prompt might suffice for a one-off task, many real-world enterprise applications require the LLM to maintain context across multiple interactions, such as a customer support chatbot or an intelligent assistant. Modern LLMs are often designed to process a "message list" or "conversation history" rather than just a single prompt.

This structured message list is where system, user, and assistant roles become essential. They help the LLM understand:

- **Who is speaking:** Is this an instruction from the application, input from the end-user, or a previous response from the AI itself?
- **The intent of each message:** Is this a general guideline, a specific request, or part of an ongoing dialogue?
- **The flow of the conversation:** By providing a chronological history of messages, the LLM can "remember" earlier parts of the interaction.

#### The System Role

The system role is typically the first message in a sequence and acts as the foundational instruction for the LLM. It defines the model's overall behavior, persona, constraints, and general rules for the entire interaction or session. This is the technical implementation of the "meta prompting" concept you learned about in Lesson 2 of this course.

- Purpose:
  - **Define Persona:** "You are an expert financial analyst."
  - **Set Global Rules:** "Always respond in a professional and concise manner."
  - **Establish Safety/Ethical Boundaries:** "Do not discuss politics or provide medical advice."
  - **Provide Constant Context:** "Responses should be based only on the provided SAP sales records."
  - **Specify Persistent Output Format:** "All generated reports must be in markdown format with headings."
- **Effectiveness:** The "system" message provides a stable "operating environment" for the LLM, ensuring consistent behavior and adherence to established guidelines throughout a conversation, regardless of subsequent user inputs. It significantly reduces "concept drift" and helps the LLM stay aligned with your application's intent.
- **Developer Aspect:** This message is usually static or semi-static within your application's code, defined once at the beginning of an interaction.

#### Example of System Message:

```json
{
  "role": "system",
  "content": "You are a helpful assistant for SAP Logistics. Your goal is to provide accurate and concise information about supply chain processes. Always refer to official SAP terminology where possible. If you don't know the answer, state that you don't have enough information."
}
```

#### The User Role

The user role represents the specific query, instruction, or context provided directly by the human interacting with your application, or by your application itself for a particular turn. This is where dynamic, real-time information is inserted.

- **Purpose:**
  - **Pose Questions:** "What is the status of sales order 12345?"
  - **Provide New Data:** "Here is the customer's purchase history: [data]."
  - **Issue Specific Commands:** "Draft an email to the client confirming shipment."
- **Effectiveness:** Clearly defines what the requestor (human or application logic) is asking or providing in that specific turn. In multi-turn scenarios, previous user messages are included in the message list to remind the LLM of the conversation's progression.
- **Developer Aspect:** This message is highly dynamic, constructed based on end-user input, data retrieved from SAP systems, or application logic for each new request to the LLM.

#### Example of User Message:

```json
{
  "role": "user",
  "content": "Explain the concept of 'material master data' in simple terms for a new employee."
}
```

#### The Assistant Role

The assistant role is crucial for maintaining conversational memory. It represents the LLM's own prior responses within an ongoing dialogue. It can also provide examples of the output expected from LLM. When building a multi-turn conversation, you send the entire history of alternating user and assistant messages back to the LLM with each new user prompt.

- **Purpose:**
  - **Maintain Context:** Allows the LLM to refer to what it or the user said previously, making conversations coherent.
  - **Continue Dialogue:** Enables the LLM to follow up on its own previous answers or acknowledge earlier parts of the conversation.
  - **Reinforce Learning (Subtly):** By including previous, well-formed assistant responses, you implicitly show the LLM examples of desirable output format, tone, and content within the specific conversation.
- **Effectiveness:** Without the assistant role, the LLM would treat each user input as a brand new, isolated request, leading to repetitive or nonsensical dialogue. This role provides the necessary "memory" for sustained interaction.
- **Developer Aspect:** You are responsible for storing and managing the conversation history, typically by appending the LLM's generated response to your message list in the assistant role before sending the next user query.

Example of assistant message (an LLM's generated response that you then send back):

```json
{
  "role": "assistant",
  "content": "Material master data in SAP refers to a central repository of information about materials that a company procures, produces, stores, and sells. It's essential for managing inventory, purchasing, production planning, and sales processes."
}
```

#### A complete example

When making an API call to an LLM, you typically send a list of messages, structured chronologically using these roles:

```json
[
  {
    "role": "system",
    "content": "You are a helpful assistant for SAP Logistics. Your goal is to provide accurate and concise information about supply chain processes. Always refer to official SAP terminology where possible. If you don't know the answer, state that you don't have enough information."
  },
  {
    "role": "user",
    "content": "Explain the concept of 'material master data' in simple terms for a new employee."
  },
  {
    "role": "assistant",
    "content": "Material master data in SAP refers to a central repository of information about materials that a company procures, produces, stores, and sells. It's essential for managing inventory, purchasing, production planning, and sales processes."
  },
  {
    "role": "user",
    "content": "That's clear, thank you. What about 'procurement process' in SAP?"
  }
]
```

The LLM would then process this entire history to generate its response to the last user message, keeping the system instructions and previous turns in mind.

### Lesson Summary

You now understand the crucial role of system, user, and assistant messages in constructing effective prompts for LLMs. You've learned how the system role sets the foundation and behavioral rules, the user role delivers direct requests, and the assistant role preserves conversational context. By utilizing this structured approach, you can create clearer instructions, maintain long-term coherence in dialogues, and significantly enhance the predictability and quality of LLM interactions within your enterprise applications.
