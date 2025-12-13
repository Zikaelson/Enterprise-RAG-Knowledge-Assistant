# 📘 Enterprise RAG Knowledge Assistant

*A secure, cloud-hosted Retrieval-Augmented Generation (RAG) backend
built on Azure for internal knowledge access and onboarding.*

------------------------------------------------------------------------

## 1. Project Purpose

The **Enterprise RAG Knowledge Assistant** is an AI-powered backend API
designed to help internal users (e.g. new hires, analysts, engineers)
ask natural language questions and receive **accurate, document-grounded
answers** from approved company documents such as:

-   IT policies\
-   Security guidelines\
-   HR manuals\
-   Onboarding materials

Unlike a generic chatbot, this system **does not hallucinate**.\
All answers are grounded in indexed enterprise documents using
**Retrieval-Augmented Generation (RAG)**.

------------------------------------------------------------------------

## 2. What This Project Solves

Traditional LLM chatbots: - Answer from training data - Cannot cite
company documents - Are risky for compliance and accuracy

This system: - Retrieves answers from **your own documents** - Provides
**citations** - Is exposed via a **secure API** - Can be integrated into
internal tools or portals

------------------------------------------------------------------------

## 3. High-Level Architecture

    Client (Browser / Postman / App)
            |
            v
    Azure Function API  (/api/ask)
            |
            v
    Azure OpenAI (Chat Completion)
            |
            v
    Azure AI Search (Vector Index)
            |
            v
    LLM Generates Grounded Answer
            |
            v
    JSON Response (Answer + Sources)

------------------------------------------------------------------------

## 4. Core Technologies Used

-   **Azure Functions (Python)** -- Serverless API backend\
-   **Azure OpenAI Service** -- LLM inference\
-   **Azure AI Search** -- Vector-based document retrieval\
-   **Application Insights** -- Logging and monitoring\
-   **Function Keys** -- API security

------------------------------------------------------------------------

## 5. Folder Structure

    azure-functions-api/
    ├── HttpTrigger/
    │   ├── __init__.py
    │   └── function.json
    ├── host.json
    ├── local.settings.json
    ├── requirements.txt
    └── .funcignore

------------------------------------------------------------------------

## 6. Security Model

-   Uses **Function Key authentication**
-   Enforced at Azure runtime level
-   No keys stored in application code
-   Unauthorized requests receive `401 Unauthorized`

------------------------------------------------------------------------

## 7. Observability

-   Request count
-   Latency
-   Exceptions
-   Execution health

All handled through **Azure Application Insights**.

------------------------------------------------------------------------

## 8. Major Roadblocks Encountered

-   GitHub deployment unsupported for Flex Consumption → switched to CLI
    deployment
-   Authentication confusion resolved via `authLevel: function`
-   Entra ID blocked due to tenant restrictions → Function Keys used
    instead

------------------------------------------------------------------------

## 9. Best Practices Followed

-   API-first design
-   Secure secret management
-   RAG-based grounding
-   Clean JSON response contracts
-   Cloud-native observability

------------------------------------------------------------------------

## 10. How to Rebuild

1.  Create Azure Resource Group\
2.  Create Azure AI Search\
3.  Create Azure OpenAI resource\
4.  Deploy model\
5.  Create Azure Function App\
6.  Configure environment variables\
7.  Index documents\
8.  Deploy function\
9.  Test with Function Key

------------------------------------------------------------------------

## 11. Intended Use Cases

-   Internal onboarding assistant\
-   Policy Q&A\
-   Secure enterprise knowledge access

------------------------------------------------------------------------

## 12. Future Enhancements

-   Entra ID authentication
-   Rate limiting
-   Frontend UI
-   Role-based access

------------------------------------------------------------------------

## Final Note

This project demonstrates **real-world AI engineering**, not a demo.
