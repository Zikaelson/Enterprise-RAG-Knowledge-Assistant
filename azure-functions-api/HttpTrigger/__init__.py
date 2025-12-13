import json
import os

import azure.functions as func
from openai import AzureOpenAI


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # 1. Get the user's question from query string or JSON body
        user_question = req.params.get("q")
        if not user_question:
            try:
                body = req.get_json()
            except ValueError:
                body = {}
            user_question = body.get("q")

        if not user_question:
            return func.HttpResponse(
                "Please provide a question in 'q' (query string or JSON body).",
                status_code=400,
            )

        # 2. Load configuration from environment variables
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        openai_key = os.environ["AZURE_OPENAI_KEY"]

        search_endpoint = os.environ["AZURE_AISEARCH_ENDPOINT"]
        search_index = os.environ["AZURE_SEARCH_INDEX"]
        search_key = os.environ["AZURE_AISEARCH_KEY"]

        # 3. Create Azure OpenAI client (API key auth)
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=openai_key,
            api_version="2024-05-01-preview",
        )

        # 4. Call Azure OpenAI with Azure AI Search as data source
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": "You are Zik Consultancy AI Assistant. Use only the company's documents.",
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

        # 5. Extract answer and return JSON
        answer = response.choices[0].message["content"]

        return func.HttpResponse(
            json.dumps({"answer": answer}),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        return func.HttpResponse(tb, status_code=500)
