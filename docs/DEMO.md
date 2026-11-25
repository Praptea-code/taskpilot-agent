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
