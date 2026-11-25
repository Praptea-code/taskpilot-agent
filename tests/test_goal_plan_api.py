import httpx


async def test_plan_and_schedule_endpoints(client: tuple[httpx.AsyncClient, object]) -> None:
    api, _ = client
    headers = {"X-User-Id": "1"}

    created = await api.post(
        "/goals",
        headers=headers,
        json={"raw_input_text": "Finish report by Friday", "domain": "general"},
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]

    planned = await api.post(f"/goals/{goal_id}/plan", headers=headers)
    assert planned.status_code == 200
    body = planned.json()
    assert body["status"] == "planned"
    assert body["clarifying_question"] is None
    assert len(body["schedule"]["actions"]) == 2
    assert body["schedule"]["actions"][0]["local_time"].startswith("2026-01-")

    schedule = await api.get(f"/goals/{goal_id}/schedule", headers=headers)
    assert schedule.status_code == 200
    assert len(schedule.json()["actions"]) == 2

    other = await api.get(f"/goals/{goal_id}/schedule", headers={"X-User-Id": "2"})
    assert other.status_code == 404


async def test_auto_plan_creates_schedule(client: tuple[httpx.AsyncClient, object]) -> None:
    api, _ = client
    created = await api.post(
        "/goals",
        headers={"X-User-Id": "1"},
        json={
            "raw_input_text": "Finish report by Friday",
            "domain": "general",
            "auto_plan": True,
        },
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]

    schedule = await api.get(f"/goals/{goal_id}/schedule", headers={"X-User-Id": "1"})
    assert schedule.status_code == 200
    assert len(schedule.json()["actions"]) == 2
