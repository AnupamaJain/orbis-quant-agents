from typing import Optional

from .base_client import BaseLLMClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .google_client import GoogleClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider (openai, anthropic, google, xai, ollama, openrouter)
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments
            - http_client: Custom httpx.Client for SSL proxy or certificate customization
            - http_async_client: Custom httpx.AsyncClient for async operations
            - timeout: Request timeout in seconds
            - max_retries: Maximum retry attempts
            - api_key: API key for the provider
            - callbacks: LangChain callbacks

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    # 1. Sanitize base_url: Clear default OpenAI endpoint if using a non-OpenAI-compatible provider
    if base_url and "api.openai.com" in base_url and provider_lower not in ("openai", "openrouter", "ollama", "xai"):
        base_url = None

    # 2. Self-healing for mismatched provider-model combinations
    model_lower = model.lower()
    mismatched = False
    if provider_lower == "google" and any(x in model_lower for x in ("gpt", "claude", "grok")):
        mismatched = True
    elif provider_lower == "openai" and any(x in model_lower for x in ("gemini", "claude", "grok")):
        mismatched = True
    elif provider_lower == "anthropic" and any(x in model_lower for x in ("gpt", "gemini", "grok")):
        mismatched = True
    elif provider_lower == "xai" and any(x in model_lower for x in ("gpt", "gemini", "claude")):
        mismatched = True

    if mismatched:
        is_quick = any(x in model_lower for x in ("mini", "nano", "flash", "haiku", "lite", "fast"))
        mode = "quick" if is_quick else "deep"
        
        default_models = {
            "google": {"quick": "gemini-2.5-flash", "deep": "gemini-2.5-pro"},
            "openai": {"quick": "gpt-5.4-mini", "deep": "gpt-5.4"},
            "anthropic": {"quick": "claude-sonnet-4-6", "deep": "claude-sonnet-4-6"},
            "xai": {"quick": "grok-4.1-fast-non-reasoning", "deep": "grok-4-0709"}
        }
        
        healed_model = default_models.get(provider_lower, {}).get(mode, model)
        print(f"[HEAL] Mismatch detected: provider '{provider}' cannot use model '{model}'. "
              f"Auto-resolved to default '{healed_model}'.", flush=True)
        model = healed_model

    if provider_lower in ("openai", "ollama", "openrouter"):
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "xai":
        return OpenAIClient(model, base_url, provider="xai", **kwargs)

    if provider_lower == "anthropic":
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        return GoogleClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
