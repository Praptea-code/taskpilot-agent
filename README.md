# taskpilot-agent

An autonomous task execution agent that turns goals into scheduled actions using free or local LLMs.

## Free LLM providers

The default provider is Ollama running locally. Any OpenAI compatible endpoint also works.

| Provider | Cost | LLM_BASE_URL | LLM_MODEL example |
| --- | --- | --- | --- |
| Ollama | free, local | http://localhost:11434 | qwen2.5:7b-instruct |
| Groq free tier | free | https://api.groq.com/openai/v1 | llama-3.1-8b-instant |
| OpenRouter free models | free | https://openrouter.ai/api/v1 | meta-llama/llama-3.2-3b-instruct:free |
| Gemini free tier | free | https://generativelanguage.googleapis.com/v1beta/openai | gemini-2.0-flash |
| llama.cpp server | free, local | http://localhost:8080/v1 | local model name |
| LM Studio | free, local | http://localhost:1234/v1 | local model name |
| vLLM | free, local | http://localhost:8000/v1 | local model name |

Example for Ollama:

```
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
LLM_MODEL=qwen2.5:7b-instruct
LLM_FALLBACK_MODEL=llama3.2:3b
```

Example for a hosted free tier:

```
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your-free-tier-key
LLM_MODEL=llama-3.1-8b-instant
```

Set `LLM_PROVIDER=fake` for deterministic offline tests and demos.
