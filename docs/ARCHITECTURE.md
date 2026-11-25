# Architecture

## Component map

```
Clients
  React web app
  curl and scripts
  voice microphone uploads

Transport
  FastAPI routers
  API key dependency
  rate limit middleware
  request logging middleware
  CORS middleware

Core
  extractor
  decomposer
  scheduler
  goal service
  renegotiator
  escalation evaluator
  monitor
  clock
  structured LLM wrapper

Executors
  local calendar
  email
  CRM
  Google Calendar stub

Providers
  Ollama client
  OpenAI compatible client
  fake offline client

Storage
  users
  goals
  tasks
  scheduled actions
  check-ins
  escalation events
  notifications
  agent sessions
  leads
  inbox messages
  user credentials
```

## Flow

A goal begins as raw text. The extractor turns it into a structured goal. The decomposer creates tasks. The scheduler places tasks into free slots and the goal service persists the goal, tasks, and scheduled actions.

The monitor polls due actions. Each executor checks completion. Unknown completion opens a check-in. A miss advances escalation and renegotiation. Renegotiation may reschedule, cancel, or ask the user. Inbound text and voice messages enter the same session or planning path.

Domain logic stays in executors and domain prompt helpers. Core modules accept generic payload builders and action types only.

## Safety boundaries

LLM output is JSON that is validated with Pydantic and retried on failure. API keys are stored as salted hashes. User credentials are encrypted with Fernet. Monitor claims prevent duplicate ticks. All rows carry `user_id` and routers filter by the authenticated user.
