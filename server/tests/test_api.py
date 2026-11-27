"""End to end through the HTTP API, seeded on startup like a fresh clone."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_demo_mode_and_the_build(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["llm_provider"] == "fake" and body["model"] == "demo"
    assert body["history_rows"] > 50000
    assert body["analytics"]["state"] == "ready" and body["analytics"]["as_of"] == "2026-11-25"
    assert body["live"]["source"] == "simulated"
    assert body["live"]["clock"].startswith("2026-11-27T12:00")
    assert body["live"]["events"] > 100


def test_network(client: TestClient) -> None:
    body = client.get("/api/network").json()
    assert len(body["trains"]) == 17 and len(body["stations"]) == 32
    ddu = next(s for s in body["stations"] if s["code"] == "DDU")
    assert 25 < ddu["lat"] < 26 and 83 < ddu["lon"] < 84


def test_chat(client: TestClient) -> None:
    examples = client.get("/api/chat/examples").json()
    assert len(examples) >= 6
    body = client.post("/api/chat", json={"message": "22448 ka status kya hai?"}).json()
    assert body["kind"] == "train_status" and body["status"]["train_no"] == "22448"
    assert body["badge"]["station"] == "NDLS" and body["answer"]
    asked = client.post("/api/chat", json={"message": "Is my train to Kanpur late?"}).json()
    assert asked["clarify"]["options"]
    follow = client.post("/api/chat", json={"message": "22448", "context": asked["context"]}).json()
    assert follow["station"] == "CNB"
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_train_status(client: TestClient) -> None:
    body = client.get("/api/trains/10147/status").json()
    assert body["status"]["state"] == "running" and body["badge"]["station"] == "MAO"
    missing = client.get("/api/trains/99999/status")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_live_board_and_unusual(client: TestClient) -> None:
    board = client.get("/api/live/board").json()
    assert len(board) == 17
    assert isinstance(client.get("/api/live/unusual").json(), list)


def test_patterns(client: TestClient) -> None:
    hotspots = client.get("/api/patterns/hotspots").json()
    assert hotspots["stations"][0]["code"] == "DDU" and hotspots["naive_top"] != "DDU"
    january = client.get("/api/patterns/hotspots", params={"months": [1]}).json()
    assert january["months"] == [1] and january["stations"][0]["code"] != "DDU"
    season = client.get("/api/patterns/seasonality").json()
    assert season["cells"] and season["windows"][0]["station"] == "DDU"
    reliability = client.get("/api/patterns/reliability").json()
    assert reliability["most_late"] == "13427" and reliability["most_on_time"] == "22973"
    card = client.get("/api/patterns/model").json()
    assert card["mae_model"] < card["mae_persistence"]
