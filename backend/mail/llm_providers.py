"""The AI services Enveliq can use for summaries.

Local servers (Ollama, LM Studio and the like) are reached on the owner's own
network. Cloud services send the text of each email to a company's servers, so
they are only ever contacted at the one fixed https address listed here, need an
access key, and need the administrator to confirm that they understand where
the mail text goes. Adding a service later means adding one entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AiProvider:
    id: str
    label: str
    cloud: bool
    blurb: str
    url: str = ""                 # fixed address for cloud services; "" = the owner types it
    url_example: str = ""         # shown for local servers
    style: str = "openai"         # "openai" (chat completions) | "anthropic" (Messages API)
    key: str = "optional"         # "none" | "optional" | "required"
    key_url: str = ""
    models_url: str = ""
    model_example: str = ""
    company: str = ""
    max_tokens_param: str = "max_tokens"
    send_temperature: bool = True
    max_tokens: int = 2000
    steps: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "cloud": self.cloud, "blurb": self.blurb, "url": self.url,
                "url_example": self.url_example, "key": self.key, "key_url": self.key_url, "models_url": self.models_url,
                "model_example": self.model_example, "company": self.company, "steps": list(self.steps)}


LOCAL = (
    AiProvider("ollama", "Ollama", False, "A model running on your own machine with Ollama.",
               url_example="http://192.168.1.20:11434/v1/chat/completions", model_example="llama3.1:8b",
               steps=("Run `ollama list` on that machine and copy a name from the NAME column.",
                      "Ollama must accept other machines: set OLLAMA_HOST=0.0.0.0 and restart it.")),
    AiProvider("lmstudio", "LM Studio", False, "A model served by LM Studio's local server.",
               url_example="http://192.168.1.20:1234/v1/chat/completions", model_example="the model's name in LM Studio",
               steps=("In LM Studio start the local server and switch on serving on the local network.",)),
    AiProvider("llamacpp", "llama.cpp server", False, "A llama.cpp server on your network.",
               url_example="http://192.168.1.20:8080/v1/chat/completions", model_example="any name your server accepts"),
    AiProvider("vllm", "vLLM", False, "A vLLM server on your network.",
               url_example="http://192.168.1.20:8000/v1/chat/completions", model_example="the name from /v1/models"),
    AiProvider("custom", "Other server on my network", False,
               "Any program that offers an OpenAI-compatible chat endpoint on your network (a router, a gateway, your own service).",
               url_example="http://192.168.1.20:8088/v1/chat/completions", model_example="the model name your server uses"),
)

CLOUD = (
    AiProvider("openai", "OpenAI", True, "ChatGPT's maker. A fast, low-cost model is plenty for summaries.",
               url="https://api.openai.com/v1/chat/completions", key="required", company="OpenAI",
               key_url="https://platform.openai.com/api-keys", models_url="https://platform.openai.com/docs/models",
               model_example="a small, inexpensive model from the models page",
               max_tokens_param="max_completion_tokens", send_temperature=False, max_tokens=4000,
               steps=("Sign in to the OpenAI platform and create an API key (it needs a payment method).",)),
    AiProvider("anthropic", "Anthropic", True, "Anthropic's own models through its own API.",
               url="https://api.anthropic.com/v1/messages", style="anthropic", key="required", company="Anthropic",
               key_url="https://console.anthropic.com/settings/keys", models_url="https://docs.anthropic.com/",
               model_example="a small, fast model from the models page",
               steps=("Sign in to the Anthropic Console and create an API key (it needs credit on the account).",
                      "A chat subscription does not include API access: the API is billed separately.")),
    AiProvider("gemini", "Google Gemini", True, "Google's Gemini models through its OpenAI-compatible endpoint.",
               url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", key="required", company="Google",
               key_url="https://aistudio.google.com/apikey", models_url="https://ai.google.dev/gemini-api/docs/models",
               model_example="a Flash model from the models page",
               steps=("Create an API key in Google AI Studio. The free tier may use what you send to improve Google's products: check its terms, or use a paid key.",)),
    AiProvider("openrouter", "OpenRouter", True, "One account and key for many models from many companies.",
               url="https://openrouter.ai/api/v1/chat/completions", key="required", company="OpenRouter (and the model's company)",
               key_url="https://openrouter.ai/keys", models_url="https://openrouter.ai/models",
               model_example="provider/model-name, copied from the models page"),
    AiProvider("groq", "Groq", True, "Very fast hosted open models.",
               url="https://api.groq.com/openai/v1/chat/completions", key="required", company="Groq",
               key_url="https://console.groq.com/keys", models_url="https://console.groq.com/docs/models",
               model_example="a model id from the models page"),
    AiProvider("mistral", "Mistral", True, "Mistral's hosted models (a European company).",
               url="https://api.mistral.ai/v1/chat/completions", key="required", company="Mistral AI",
               key_url="https://console.mistral.ai/api-keys", models_url="https://docs.mistral.ai/getting-started/models/models_overview/",
               model_example="a small model id from the models page"),
    AiProvider("xai", "xAI (Grok)", True, "Grok models from xAI.",
               url="https://api.x.ai/v1/chat/completions", key="required", company="xAI",
               key_url="https://console.x.ai", models_url="https://docs.x.ai/docs/models",
               model_example="a model id from the models page"),
    AiProvider("deepseek", "DeepSeek", True, "DeepSeek's hosted models.",
               url="https://api.deepseek.com/chat/completions", key="required", company="DeepSeek",
               key_url="https://platform.deepseek.com/api_keys", models_url="https://api-docs.deepseek.com/quick_start/pricing",
               model_example="a model id from the models page"),
    AiProvider("together", "Together AI", True, "Hosted open models from Together AI.",
               url="https://api.together.xyz/v1/chat/completions", key="required", company="Together AI",
               key_url="https://api.together.ai/settings/api-keys", models_url="https://docs.together.ai/docs/serverless-models",
               model_example="a model id from the models page"),
)

PROVIDERS: tuple[AiProvider, ...] = LOCAL + CLOUD
BY_ID = {p.id: p for p in PROVIDERS}


def get(provider_id: str | None) -> AiProvider:
    """The provider with this id; anything unknown is treated as a server on the owner's network."""
    return BY_ID.get(provider_id or "custom", BY_ID["custom"])
