# import json
# import os

# import azure.functions as func
# from openai import AzureOpenAI


# def main(req: func.HttpRequest) -> func.HttpResponse:
#     try:
#         # 1. Get the user's question from query string or JSON body
#         user_question = req.params.get("q")
#         if not user_question:
#             try:
#                 body = req.get_json()
#             except ValueError:
#                 body = {}
#             user_question = body.get("q")

#         if not user_question:
#             return func.HttpResponse(
#                 "Please provide a question in 'q' (query string or JSON body).",
#                 status_code=400,
#             )

#         # 2. Load configuration from environment variables
#         endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
#         deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
#         openai_key = os.environ["AZURE_OPENAI_KEY"]

#         search_endpoint = os.environ["AZURE_AISEARCH_ENDPOINT"]
#         search_index = os.environ["AZURE_SEARCH_INDEX"]
#         search_key = os.environ["AZURE_AISEARCH_KEY"]

#         # 3. Create Azure OpenAI client (API key auth)
#         client = AzureOpenAI(
#             azure_endpoint=endpoint,
#             api_key=openai_key,
#             api_version="2024-05-01-preview",
#         )

#         # 4. Call Azure OpenAI with Azure AI Search as data source
#         response = client.chat.completions.create(
#             model=deployment,
#             messages=[
#                 {
#                     "role": "system",
#                     "content": "You are Zik Consultancy AI Assistant. Use only the company's documents.",
#                 },
#                 {"role": "user", "content": user_question},
#             ],
#             extra_body={
#                 "data_sources": [
#                     {
#                         "type": "azure_search",
#                         "parameters": {
#                             "endpoint": search_endpoint,
#                             "index_name": search_index,
#                             "authentication": {
#                                 "type": "api_key",
#                                 "key": search_key,
#                             },
#                         },
#                     }
#                 ]
#             },
#         )

#         # 5. Extract answer and return JSON
#         answer = response.choices[0].message.content

#         return func.HttpResponse(
#             json.dumps({"answer": answer}),
#             mimetype="application/json",
#             status_code=200,
#         )

#     except Exception as e:
#         import traceback
#         tb = traceback.format_exc()
#         print(tb)
#         return func.HttpResponse(tb, status_code=500)



import json
import os
import azure.functions as func
from openai import AzureOpenAI


def _safe_model_dump(obj):
    """
    Tries to convert SDK objects into plain dicts safely.
    Works across OpenAI SDK versions.
    """
    if obj is None:
        return None
    # Newer pydantic-based objects
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    # Older versions sometimes have to_dict()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    # Last resort: try JSON serialization fallback
    try:
        return json.loads(json.dumps(obj, default=lambda x: getattr(x, "__dict__", str(x))))
    except Exception:
        return {"_unserializable": str(obj)}


def _find_citations(resp_dict: dict):
    """
    Azure "On your data" citations appear in different places depending on API/SDK.
    We check the most common locations and return a list of citation dicts.
    """
    if not isinstance(resp_dict, dict):
        return []

    citations = []

    # Most common: choices[0].message.context.citations (Azure OpenAI "on your data")
    try:
        ctx = (
            resp_dict.get("choices", [{}])[0]
            .get("message", {})
            .get("context", {})
        )
        cits = ctx.get("citations", [])
        if isinstance(cits, list):
            citations.extend(cits)
    except Exception:
        pass

    # Sometimes: choices[0].message.model_extra.context.citations (SDK variations)
    # model_extra isn't always in model_dump; but if it is, it may show here.
    try:
        msg = resp_dict.get("choices", [{}])[0].get("message", {})
        extra_ctx = msg.get("model_extra", {}).get("context", {})
        cits = extra_ctx.get("citations", [])
        if isinstance(cits, list):
            citations.extend(cits)
    except Exception:
        pass

    # Sometimes: resp has a top-level "citations"
    try:
        cits = resp_dict.get("citations", [])
        if isinstance(cits, list):
            citations.extend(cits)
    except Exception:
        pass

    # De-dup by a stable key if present
    seen = set()
    unique = []
    for c in citations:
        if not isinstance(c, dict):
            continue
        key = (
            c.get("id")
            or c.get("chunk_id")
            or c.get("filepath")
            or c.get("title")
            or json.dumps(c, sort_keys=True)
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    return unique


def _normalize_citations(citations: list):
    """
    Normalizes raw citations into a stable UI-friendly schema.
    """
    normalized = []
    for c in citations:
        if not isinstance(c, dict):
            continue

        normalized.append({
            # Common fields seen in Azure citations
            "title": c.get("title") or c.get("file") or c.get("filename") or None,
            "filepath": c.get("filepath") or c.get("path") or None,
            "url": c.get("url") or c.get("source_url") or None,
            "chunk_id": c.get("chunk_id") or c.get("id") or None,
            "content": c.get("content") or c.get("excerpt") or c.get("text") or None,
        })

    return normalized


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ---- 1) Input ----
        user_question = req.params.get("q")
        if not user_question:
            try:
                body = req.get_json()
            except ValueError:
                body = {}
            user_question = body.get("q")

        if not user_question or not str(user_question).strip():
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing 'q'. Provide ?q=... or JSON body {'q': '...'}"
                }),
                mimetype="application/json",
                status_code=400
            )

        # ---- 2) Config ----
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        openai_key = os.environ["AZURE_OPENAI_KEY"]

        search_endpoint = os.environ["AZURE_AISEARCH_ENDPOINT"]
        search_index = os.environ["AZURE_SEARCH_INDEX"]
        search_key = os.environ["AZURE_AISEARCH_KEY"]

        # ---- 3) Client ----
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=openai_key,
            api_version="2024-05-01-preview",
        )

        # ---- 4) RAG Call ----
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Zik Consultancy AI Assistant. "
                        "Answer ONLY using the documents in Azure AI Search. "
                        "If the answer is not in the documents, say: 'I don't know based on the provided documents.' "
                        "Where possible, ground key claims in citations."
                    ),
                },
                {"role": "user", "content": user_question},
            ],
            extra_body={
                "data_sources": [
                    {
                        "type": "azure_search",
                        "parameters": {
                            "endpoint": search_endpoint,
                            "index_name": search_index,
                            "authentication": {
                                "type": "api_key",
                                "key": search_key,
                            },
                        },
                    }
                ]
            },
        )

        # ---- 5) Extract answer + citations ----
        answer = response.choices[0].message.content

        resp_dict = _safe_model_dump(response)
        raw_citations = _find_citations(resp_dict)
        citations = _normalize_citations(raw_citations)

        # Try to expose a request id for troubleshooting if present
        request_id = None
        try:
            request_id = resp_dict.get("id")
        except Exception:
            request_id = None

        return func.HttpResponse(
            json.dumps({
                "answer": answer,
                "citations": citations,
                "raw_citations_found": len(raw_citations),
                "request_id": request_id,
            }),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        # Return a readable error without leaking secrets
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )
