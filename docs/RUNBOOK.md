# Runbook

## Daily checks

- Call `GET /health` and confirm the version matches the deployed release.
- Query recent `Notification` and `EscalationEvent` rows for unusual volume.
- Query `ScheduledAction` rows with a `scheduled_at` far in the past and a status other than `DONE`.
- Confirm the monitor process is the only scheduler-enabled replica.

## Common operations

### Apply a schema change

Back up the database, stop the API, then run:

```
python -m alembic upgrade head
```

Start the API after the migration succeeds.

### Recover overdue actions

Normal startup clears monitor claims older than `MONITOR_LOCK_MINUTES`. If a process stopped mid tick and the lock is recent, wait for the window or lower the value deliberately, then restart one API process.

### Rotate a user API key

Create a replacement key for the user by issuing a new user record with a unique email, or run a small script that writes a new salt and hash to the existing user. Return the plain token once and discard it after the client stores it.

### Rotate the credentials encryption key

Decrypt all rows in `user_credentials` with the old key, set the new `CREDENTIALS_KEY`, then encrypt and write them again. Keep the API stopped during rotation.

### Reset the offline demo

Delete `demo_sales.db` and run:

```
make demo-offline
```

## Incident response

- Bad LLM output: switch `LLM_MODEL` to the recommended model or use `LLM_PROVIDER=fake` while investigating.
- Duplicate reschedules: confirm one scheduler process and inspect `processing_at` and `attempt_number` on affected actions.
- Email not delivered: check `SMTP_CONSOLE`, SMTP credentials, and the Mailpit inbox on port 8025.
- Rate limit storms: raise `RATE_LIMIT_PER_MINUTE` or place a trusted proxy ahead of the API.
- Unhandled errors: logs are JSON lines with request context and exception details.
