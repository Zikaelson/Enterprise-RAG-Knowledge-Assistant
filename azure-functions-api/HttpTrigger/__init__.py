import json
import azure.functions as func
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
import os

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        user_question = req.params.get("q")
        if not user_question:
            body = req.get_json()
            user_question = body.get("q")

        # Azure OpenAI configuration
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
        search_index = os.environ["AZURE_SEARCH_INDEX"]

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            f"{os.environ['AZURE_OPENAI_RESOURCE']}.default"
        )

        client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version="2024-05-01-preview"
        )

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are Zik Consultancy AI Assistant. Use only the company's documents."},
                {"role": "user", "content": user_question}
            ],
            extra_body={
                "data_sources": [
                    {
                        "type": "azure_search",
                        "parameters": {
                            "endpoint": search_endpoint,
                            "index_name": search_index,
                            "authentication": {
                                "type": "system_assigned_managed_identity"
                            }
                        }
                    }
                ]
            }
        )

        answer = response.choices[0].message["content"]
        return func.HttpResponse(answer, status_code=200)

    except Exception as e:
        return func.HttpResponse(str(e), status_code=500)
