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
