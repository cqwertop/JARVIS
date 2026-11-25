"""Online AI providers KAIRO can use with an API key.

Anthropic (Claude) has its own API. Most other companies offer an "OpenAI-compatible" API (the same request
format OpenAI uses), so one client covers all of them: OpenAI, Google Gemini, OpenRouter, Groq, Mistral,
DeepSeek, xAI, or any other compatible service you give the address of.

Model names change often, so KAIRO doesn't hard-code them: after your key is checked, it asks the provider
which models your key can use and suggests one (see suggest_model).
"""

import json
import re
import urllib.error
import urllib.request

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "label": "Anthropic Claude", "kind": "anthropic", "key_prefix": "sk-ant-",
        "base_url": "https://api.anthropic.com", "prefer": ["claude-sonnet-5-5", "claude-sonnet", "claude-opus"],
        "key_url": "https://console.anthropic.com/settings/keys", "site": "Anthropic Console",
        "blurb": "Claude - very capable at conversation and using tools. Pay per use.",
    },
    "openai": {
        "label": "OpenAI", "kind": "openai", "base_url": "https://api.openai.com/v1", "key_prefix": "sk-",
        "key_url": "https://platform.openai.com/api-keys", "site": "OpenAI Platform",
        "blurb": "The company behind ChatGPT. Pay per use - separate from a ChatGPT Plus subscription.",
        "prefer": ["gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"],
    },
    "gemini": {
        "label": "Google Gemini", "kind": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "key_prefix": "AIza",
        "key_url": "https://aistudio.google.com/apikey", "site": "Google AI Studio",
        "blurb": "Google's AI. Has a free tier with daily limits.",
        "prefer": ["gemini-2.5-flash", "gemini-flash-latest", "flash", "gemini-2.5-pro", "pro"],
    },
    "openrouter": {
        "label": "OpenRouter", "kind": "openai", "base_url": "https://openrouter.ai/api/v1", "key_prefix": "sk-or-",
        "key_url": "https://openrouter.ai/keys", "site": "OpenRouter",
        "blurb": "One key for models from many companies. Some models are free.",
        "prefer": ["openai/gpt-5-mini", "anthropic/claude", "google/gemini", "openai/"],
    },
    "groq": {
        "label": "Groq", "kind": "openai", "base_url": "https://api.groq.com/openai/v1", "key_prefix": "gsk_",
        "key_url": "https://console.groq.com/keys", "site": "GroqCloud",
        "blurb": "Very fast answers from open models. Has a free tier.",
        "prefer": ["llama-3.3-70b", "llama", "qwen", "gpt-oss"],
    },
    "mistral": {
        "label": "Mistral AI", "kind": "openai", "base_url": "https://api.mistral.ai/v1", "key_prefix": "",
        "key_url": "https://console.mistral.ai/api-keys", "site": "Mistral console",
        "blurb": "European AI company. Pay per use, with a free experiment tier.",
        "prefer": ["mistral-medium-latest", "mistral-small-latest", "mistral-large-latest"],
    },
    "deepseek": {
        "label": "DeepSeek", "kind": "openai", "base_url": "https://api.deepseek.com/v1", "key_prefix": "sk-",
        "key_url": "https://platform.deepseek.com/api_keys", "site": "DeepSeek Platform",
        "blurb": "Low-cost models. Pay per use.", "prefer": ["deepseek-chat"],
    },
    "xai": {
        "label": "xAI Grok", "kind": "openai", "base_url": "https://api.x.ai/v1", "key_prefix": "xai-",
        "key_url": "https://console.x.ai", "site": "xAI console", "blurb": "Grok models. Pay per use.",
        "prefer": ["grok-4", "grok-3", "grok"],
    },
    "custom": {
        "label": "Another service", "kind": "openai", "base_url": "", "key_prefix": "", "key_url": "",
        "site": "", "blurb": "Any service with an OpenAI-compatible API. You'll need its web address (base URL).",
        "prefer": [],
    },
}

# Models that can't hold a conversation (images, audio, embeddings...). Hidden from the model list.
_NOT_CHAT = re.compile(r"embed|whisper|tts|dall-e|image|audio|moderation|realtime|transcribe|search|vision-preview|"
                       r"davinci|babbage|computer-use|guard|aqa|imagen|veo|-tts|speech", re.I)


def credential_name(provider_id: str) -> str:
    return "anthropic_api_key" if provider_id == "anthropic" else f"{provider_id}_api_key"


class ProviderError(Exception):
    """User-readable problem talking to a provider."""


def explain_http_error(code: int, body: str, provider_label: str) -> str:
    text = body.lower()
    if code in (401, 403) and ("key" in text or "auth" in text or code == 401):
        return (f"{provider_label} didn't accept this key. Copy the whole key again, with no spaces, and check it "
                "hasn't been deleted.")
    if code == 402 or "billing" in text or "credit" in text or "insufficient_quota" in text or "quota" in text:
        return f"The key works, but the {provider_label} account has no credit or has run out of quota. Check billing."
    if code == 429:
        return f"{provider_label} says there have been too many requests. Wait a minute and try again."
    if code == 404:
        return "That address or model wasn't found. Check the service's web address and the model name."
    if code >= 500:
        return f"{provider_label} is having problems right now. Try again in a few minutes."
    return f"{provider_label} returned an error ({code}): {body[:160]}"


def _request(url: str, key: str, payload: dict | None = None, timeout: float = 60) -> dict:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def list_models(base_url: str, key: str, label: str = "The service") -> list[str]:
    """Check the key (listing models is free) and return the chat models it can use."""
    try:
        data = _request(base_url.rstrip("/") + "/models", key, timeout=20)
    except urllib.error.HTTPError as exc:
        raise ProviderError(explain_http_error(exc.code, exc.read().decode(errors="ignore"), label)) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Couldn't reach {label}. Check your internet connection"
                            f"{' and the web address' if 'localhost' not in base_url else ''}.") from exc
    except ValueError as exc:
        raise ProviderError(f"{label} sent an answer KAIRO didn't understand. Check the web address.") from exc
    ids = [m.get("id", "").removeprefix("models/") for m in data.get("data", data.get("models", []))]
    return sorted({i for i in ids if i and not _NOT_CHAT.search(i)})


def suggest_model(provider_id: str, models: list[str]) -> str:
    prefer = PROVIDERS.get(provider_id, {}).get("prefer", [])
    for p in prefer:
        exact = [m for m in models if m == p]
        if exact:
            return exact[0]
        partial = sorted((m for m in models if p in m), key=len)
        if partial:
            return partial[0]
    return models[0] if models else ""
