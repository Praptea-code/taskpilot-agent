# Decisions

- Commit 19: `POST /goals/{id}/plan` updates the existing goal instead of creating a second goal. `GoalService.create_goal_plan` accepts an optional `goal` row for this path.
- Commit 20: fake demo mode supplies canned JSON responses because the environment-selected `FakeLLMClient` has no scripted queue by default.
