# Demo

## Ollama quick start

Install and start Ollama, then pull the default local model:

```
ollama serve
ollama pull qwen2.5:7b-instruct
```

Install the project and apply migrations:

```
make install
make migrate
```

Run the calendar demo. The script prompts for a goal if none is supplied:

```
make demo-calendar
make demo-calendar ARGS="--goal 'Prepare the quarterly report by tomorrow'"
```

The demo uses the configured LLM, creates local calendar events in SQLite, and prints the scheduled actions with times in the user timezone.

## Offline fake demo

No LLM or network is needed with canned responses:

```
make demo-calendar ARGS="--fake --goal 'Prepare the quarterly report by tomorrow'"
```

Or select the fake provider through the environment:

```
LLM_PROVIDER=fake python scripts/demo_calendar.py --goal "Prepare the quarterly report by tomorrow"
```

## Sales follow-up demo

The sales demo seeds five leads, creates one `send_email` action per lead, sends the first touches to the console backend, adds simulated replies, then runs the monitor to mark the actions complete:

```
make demo-sales
make demo-sales ARGS="--fake"
LLM_PROVIDER=fake python scripts/demo_sales.py
```

Set `SMTP_CONSOLE=false` and point `SMTP_HOST` at Mailpit when you want to inspect messages in a local inbox instead of the console.

## Optional voice

Install the optional speech extras:

```
python -m pip install -e ".[voice]"
```

Download a free Piper voice from https://huggingface.co/rhasspy/piper-voices and set the model path:

```
PIPER_MODEL=/path/to/en_US-lessac-medium.onnx
WHISPER_MODEL=base.en
```

When Piper is not configured, text to speech returns the reply text bytes instead of audio.

## React client

Install dependencies and start the dev server:

```
cd web
npm install
npm run dev
```

The client runs at `http://localhost:5173` and proxies API calls to FastAPI on port 8000. Start the API with `make dev` in another terminal. Create a goal, send a chat message, refresh notifications, and press Mic to send a recorded audio clip to the voice endpoint.

When `API_KEY` is set on the server, enter the same value in the client. It is sent as `X-API-Key` on every request.
