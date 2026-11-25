# Deployment

## Application process

Install runtime dependencies and apply migrations before starting the API:

```
python -m pip install -e .
python -m alembic upgrade head
uvicorn agent.main:app --host 0.0.0.0 --port 8000
```

Do not run more than one scheduler-enabled process against the same database. The in-process scheduler reuses one `ScheduledAction` per check-in cycle, so multiple replicas would duplicate monitor ticks.

Use a reverse proxy with TLS in production. Keep the API bound to localhost or a private network if the proxy runs on the same host.

## Environment

Set `DEV_MODE=false` in production so only bearer API keys are accepted. Create users with `POST /users` and store the returned one-time key in the client. The server keeps only a salted SHA-256 hash.

For hosted free LLM tiers, set `LLM_PROVIDER=openai_compat` plus `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. For local inference, keep `LLM_PROVIDER=ollama` and point `OLLAMA_HOST` at the Ollama service.

Tune `RATE_LIMIT_PER_MINUTE` for the reverse proxy and expected client count. The limiter is in memory, so it resets on restart and is per process.

Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and set it as `CREDENTIALS_KEY`. POST secrets to `/users/me/credentials`; the API stores ciphertext and never returns secret values.

`GoogleCalendarExecutor` is a stub that satisfies the executor interface. To enable it later, register a Google OAuth client, store the resulting token as a credential with service `google_calendar`, implement the API calls in that class, and keep the OAuth consent screen in testing mode for free usage.

Set `SMTP_CONSOLE=false` to send real email. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_SENDER`. Replies are read from the local `inbox_messages` table, so an external mail integration should insert into that table.

Voice requires `python -m pip install -e ".[voice]"` and a Piper voice file. Set `WHISPER_MODEL` and `PIPER_MODEL`. Without Piper, voice replies contain plain text bytes.

## Database

SQLite is the default. For Postgres, set:

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/taskpilot
```

Create the schema on a fresh deployment with:

```
python -m alembic upgrade head
```

Back up the database before upgrades. For SQLite, copy the database file while the service is stopped. For Postgres, use `pg_dump` and keep the output outside the application directory.

## Health checks

Use `GET /health` for liveness. It returns the application version and does not require a user API key.

Logs are JSON lines with `user_id`, `goal_id`, `action_id`, and `path` when available. Unhandled exceptions return a generic 500 response and log the full exception.

Monitor logs for failed check-ins, escalation level changes, and notification delivery errors. Each tick claims actions with `processing_at`, so two ticks cannot reschedule the same action twice. Claims older than `MONITOR_LOCK_MINUTES` are cleared on startup.

## Web client

Build static assets with:

```
cd web
npm install
npm run build
```

Serve `web/dist` through any static file server. The Vite dev proxy is only for development. In production, point the client at the public API origin and allow that browser origin in the `CORSMiddleware` list in `agent.main`.

## systemd example

```
[Unit]
Description=TaskPilot Agent
After=network.target

[Service]
User=taskpilot
WorkingDirectory=/opt/taskpilot
EnvironmentFile=/opt/taskpilot/.env
ExecStart=/opt/taskpilot/.venv/bin/uvicorn agent.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## Docker notes

Build an image from the project root and run one container. Mount a volume for SQLite or use Postgres. Pass configuration with environment variables or an env file. Do not bake `.env`, API keys, or database files into the image.
