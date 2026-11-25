# taskpilot-agent

An autonomous task execution agent that turns goals into scheduled actions using free or local LLMs.

## Quickstart

Requirements: Python 3.12, Node 20 or newer, and Ollama for local inference.

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic upgrade head
make dev
```

The API listens on `http://localhost:8000`. Check it with:

```
curl http://localhost:8000/health
```

Create a user and keep the one-time API key from the response:

```
curl -X POST http://localhost:8000/users ^
  -H "Content-Type: application/json" ^
  -d "{\"name\": \"Demo User\", \"email\": \"demo@example.com\"}"
```

Use that key as a bearer token:

```
curl -X POST http://localhost:8000/goals ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer YOUR_API_KEY" ^
  -d "{\"raw_input_text\": \"Prepare the quarterly review\", \"domain\": \"general\", \"auto_plan\": false}"

curl -X POST http://localhost:8000/goals/1/plan ^
  -H "Authorization: Bearer YOUR_API_KEY"
```

Start the web client:

```
cd web
npm install
npm run dev
```

The client runs on `http://localhost:5173` and proxies API calls to port 8000.

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

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./agent.db` | SQLAlchemy database URL |
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai_compat`, or `fake` |
| `LLM_MODEL` | `qwen2.5:7b-instruct` | Primary model |
| `LLM_FALLBACK_MODEL` | `llama3.2:3b` | Fallback model |
| `LLM_BASE_URL` | `http://localhost:11434` | OpenAI compatible base URL |
| `LLM_API_KEY` | empty | Key for hosted compatible endpoints |
| `TIMEZONE` | `UTC` | Default user timezone |
| `GRACE_MINUTES` | `10` | Late reply grace window |
| `SMTP_CONSOLE` | `true` | Print email instead of sending it |
| `SMTP_HOST` | `localhost` | SMTP host |
| `SMTP_PORT` | `1025` | SMTP port |
| `WHISPER_MODEL` | `base.en` | faster-whisper model name |
| `PIPER_MODEL` | empty | Piper ONNX model path |
| `DEV_MODE` | `true` | Allows `X-User-Id` for local tests only |
| `RATE_LIMIT_PER_MINUTE` | `120` | Sliding-window request limit per client |
| `CREDENTIALS_KEY` | empty | Fernet key for encrypted per-user credentials |

Copy `.env.example` to `.env` and edit only the values you need.

## Demos and checks

```
make check
make demo-sales
make demo-offline
python -m alembic upgrade head
```

See `docs/DEMO.md` for the offline sales demo and optional voice setup. See `docs/DEPLOYMENT.md` for production notes.
