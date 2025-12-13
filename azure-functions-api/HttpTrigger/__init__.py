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
import re
import html

import azure.functions as func
from openai import AzureOpenAI


def clean_text(s: str) -> str:
    """Cleans text for UI: unescape HTML, normalize whitespace/newlines."""
    if not s:
        return ""
    s = html.unescape(s)                 # &amp; -> &
    s = s.replace("\r\n", "\n")
    s = re.sub(r"[ \t]+", " ", s)        # collapse spaces/tabs
    s = re.sub(r"\n{3,}", "\n\n", s)     # collapse excessive newlines
    return s.strip()


def excerpt_around_keyword(text: str, keyword: str, max_chars: int = 700) -> str:
    """
    Returns a short, readable excerpt from a long citation.
    Tries to center around the first occurrence of keyword; otherwise returns start.
    """
    text = clean_text(text)
    if not text:
        return ""

    if not keyword:
        return text[:max_chars] + ("..." if len(text) > max_chars else "")

    idx = text.lower().find(keyword.lower())
    if idx == -1:
        snippet = text[:max_chars]
        return snippet + ("..." if len(text) > max_chars else "")

    start = max(idx - int(max_chars * 0.35), 0)
    end = min(start + max_chars, len(text))
    snippet = text[start:end]

    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _safe_model_dump(obj):
    """Convert SDK objects into plain dicts across OpenAI SDK versions."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    try:
        return json.loads(json.dumps(obj, default=lambda x: getattr(x, "__dict__", str(x))))
    except Exception:
        return {"_unserializable": str(obj)}


def _find_citations(resp_dict: dict):
    """Find Azure On-Your-Data citations across common response shapes."""
    if not isinstance(resp_dict, dict):
        return []

    citations = []

    # Common: choices[0].message.context.citations
    try:
        ctx = resp_dict.get("choices", [{}])[0].get("message", {}).get("context", {})
        cits = ctx.get("citations", [])
        if isinstance(cits, list):
            citations.extend(cits)
    except Exception:
        pass

    # Sometimes: top-level citations
    try:
        cits = resp_dict.get("citations", [])
        if isinstance(cits, list):
            citations.extend(cits)
    except Exception:
        pass

    # De-dup
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


def _normalize_citations(citations: list, user_question: str):
    """
    Normalize raw citations into stable schema + clean, short excerpt.
    We prefer excerpts around likely anchors (Classification) or the user's query.
    """
    normalized = []
    q_anchor = (user_question or "").strip()
    for c in citations:
        if not isinstance(c, dict):
            continue

        title = c.get("title") or c.get("file") or c.get("filename") or None
        filepath = c.get("filepath") or c.get("path") or None
        url = c.get("url") or c.get("source_url") or None
        chunk_id = c.get("chunk_id") or c.get("id") or None

        raw = c.get("content") or c.get("excerpt") or c.get("text") or ""

        # Pick a good anchor for excerpting:
        # 1) "Classification" (works for your policy docs)
        # 2) fall back to user's question if it's short enough
        anchor = "Classification"
        if q_anchor and len(q_anchor) <= 80:
            anchor = q_anchor

        content = excerpt_around_keyword(raw, anchor, max_chars=700)

        normalized.append({
            "source_id": chunk_id,
            "title": title,
            "filepath": filepath,
            "url": url,
            "chunk_id": chunk_id,
            "content": content
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
                        "Answer ONLY using the documents provided via Azure AI Search. "
                        "If the answer is not present, say: \"I don't know based on the provided documents.\" "
                        "Do NOT include bracket tags like [doc1]; citations are returned separately. "
                        "Keep answers concise and structured."
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
                            # Optional tuning knobs (safe defaults)
                            "top_n_documents": 5,
                            "strictness": 3
                        },
                    }
                ]
            },
        )

        # ---- 5) Extract answer + clean doc tags just in case ----
        answer = response.choices[0].message.content or ""
        answer = re.sub(r"\s*\[doc\d+\]", "", answer).strip()

        # ---- 6) Extract citations + normalize for UI ----
        resp_dict = _safe_model_dump(response)
        raw_citations = _find_citations(resp_dict)
        citations = _normalize_citations(raw_citations, user_question)

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
        # Production-safe: return error string without secrets
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500,
        )
