"""Select the configured structured-model provider without coupling workflows to it."""

from app.ai.ollama_provider import OllamaStructuredProvider
from app.ai.openai_provider import OpenAIResponsesProvider
from app.ai.provider import StructuredModelProvider
from app.core.config import Settings


def provider_is_configured(settings: Settings) -> bool:
    return settings.planning_ai_configured


def build_structured_model_provider(settings: Settings) -> StructuredModelProvider | None:
    if not provider_is_configured(settings):
        return None
    if settings.ai_provider == "ollama":
        return OllamaStructuredProvider(settings)
    if settings.ai_provider == "openai":
        return OpenAIResponsesProvider(settings)
    return None
