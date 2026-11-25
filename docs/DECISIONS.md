# Decisions

- Commit 19: `POST /goals/{id}/plan` updates the existing goal instead of creating a second goal. `GoalService.create_goal_plan` accepts an optional `goal` row for this path.
- Commit 20: fake demo mode supplies canned JSON responses because the environment-selected `FakeLLMClient` has no scripted queue by default.
- Commit 21: the APScheduler job uses a module-level tick function because the `Monitor` instance holds an async engine that `SQLAlchemyJobStore` cannot pickle.
- Commit 22: an unknown completion result sets the action to `in_progress` after creating a check-in notification, so later ticks wait for the user reply.
- Commit 23: a rescheduled check-in applies an ISO `new_time` directly when present, otherwise it leaves the action waiting in `in_progress`.
- Commit 24: miss history in the renegotiation context comes from `Task.miss_count` for every task in the goal.
- Commit 25: an invalid proposed time is asked for once, then replaced by the greedy scheduler's first available slot if it is still invalid.
- Commit 27: renegotiation messages are sent through `TextChannel`, and an `ask_user` decision opens an `agent_sessions` row in `awaiting_reply`.
- Commit 28: session turns are stored in `AgentSession.context` under `turns`, trimmed to the latest 10 entries after each reply.
- Commit 29: escalation policy overrides merge into defaults by level number, so a partial level override keeps the default channel and contact list.
- Commit 30: escalation level advances one step per miss after the threshold and stops at the highest configured level.
- Commit 31: escalation messages fall back to a tone-prefixed template when the LLM is unavailable, so notifications never depend on model uptime.
- Commit 32: email delivery defaults to a console backend, and SMTP settings are only used when `SMTP_CONSOLE=false`.
- Commit 33: the escalation scenario advances the clock between misses and reuses one scheduled action across every step.
- Commit 34: `send_email` tasks store `lead_id`, `template`, and `step` in `Task.payload`, validated by `SendEmailPayload`.
- Commit 35: reply checks use a local `inbox_messages` table, with a three-day minimum gap and weekday-only availability for follow-ups.
- Commit 36: CRM updates are stage transitions stored in `Task.payload`, and completion means the lead already reached the target stage.
- Commit 37: domain examples and payload builders live in `executors.domain_prompts`, so core only calls generic helpers.
