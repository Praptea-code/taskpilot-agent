from agent.config import Settings, get_settings
from agent.llm.base import LLMClient
from agent.llm.fake import FakeLLMClient


def get_llm(settings: Settings | None = None) -> LLMClient:
    current = settings or get_settings()
    provider = current.llm_provider
    if provider == "fake":
        return FakeLLMClient()
    if provider == "ollama":
        from agent.llm.ollama import OllamaClient

        return OllamaClient(
            host=current.ollama_host,
            model=current.llm_model,
            fallback_model=current.llm_fallback_model,
        )
    if provider == "openai_compat":
        from agent.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient(
            base_url=current.llm_base_url,
            api_key=current.llm_api_key,
            model=current.llm_model,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")
