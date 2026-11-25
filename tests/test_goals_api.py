import httpx


async def test_goals_are_isolated_by_user(client: tuple[httpx.AsyncClient, object]) -> None:
    api, _ = client
    headers_a = {"X-User-Id": "1"}
    headers_b = {"X-User-Id": "2"}

    created = await api.post(
        "/goals",
        headers=headers_a,
        json={"raw_input_text": "Plan a trip", "domain": "general"},
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    own = await api.get(f"/goals/{goal_id}", headers=headers_a)
    assert own.status_code == 200
    assert own.json()["raw_input_text"] == "Plan a trip"

    other = await api.get(f"/goals/{goal_id}", headers=headers_b)
    assert other.status_code == 404

    list_a = await api.get("/goals", headers=headers_a)
    list_b = await api.get("/goals", headers=headers_b)
    assert len(list_a.json()) == 1
    assert list_b.json() == []


async def test_missing_user_header_is_rejected(client: tuple[httpx.AsyncClient, object]) -> None:
    api, _ = client
    response = await api.get("/goals")
    assert response.status_code == 401
