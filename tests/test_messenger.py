from io import BytesIO

import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import make_user


def test_home_and_auth(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
    uid, auth = make_user(client, "alice")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth).json()["id"] == uid
    assert client.post("/api/v1/auth/register", json={
        "username": "ALICE", "display_name": "Other", "password": "very-secret-password"
    }).status_code == 409
    assert client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "wrong"
    }).status_code == 401
    assert client.patch("/api/v1/users/me", headers=auth, json={"bio": "coding after midnight"}).json()["bio"] == "coding after midnight"
    assert client.get("/api/v1/users/online", headers=auth).json() == {"count": 0, "users": []}


def test_dms_history_status_threads_and_permissions(client):
    alice_id, alice = make_user(client, "alice")
    bob_id, bob = make_user(client, "bob")
    eve_id, eve = make_user(client, "eve")

    # Separate persistent DM and status thread, both private to Alice + Bob.
    status_response = client.post("/api/v1/statuses", headers=bob, json={"text": "Anyone coding?"})
    assert status_response.status_code == 201, status_response.text
    status_id = status_response.json()["id"]
    assert client.get(f"/api/v1/users/{bob_id}/statuses", headers=alice).json()[0]["text"] == "Anyone coding?"

    direct = client.post("/api/v1/conversations", headers=alice, json={"recipient_id": bob_id})
    assert direct.status_code == 200, direct.text
    direct_id = direct.json()["id"]
    duplicate = client.post("/api/v1/conversations", headers=bob, json={"recipient_id": alice_id})
    assert duplicate.json()["id"] == direct_id

    status_thread = client.post("/api/v1/conversations", headers=alice, json={
        "recipient_id": bob_id, "status_id": status_id,
    })
    assert status_thread.status_code == 200, status_thread.text
    assert status_thread.json()["id"] != direct_id
    assert status_thread.json()["status"]["text"] == "Anyone coding?"
    assert client.post("/api/v1/conversations", headers=eve, json={
        "recipient_id": alice_id, "status_id": status_id,
    }).status_code == 400

    for idx in range(25):
        r = client.post(f"/api/v1/conversations/{direct_id}/messages", headers=alice, json={"text": f"Hello {idx}"})
        assert r.status_code == 201, r.text
    recent = client.get(f"/api/v1/conversations/{direct_id}/messages?limit=10&offset=0", headers=bob).json()
    assert recent["total"] == 25 and recent["has_more"] is True
    assert recent["items"][0]["text"] == "Hello 24" and recent["items"][-1]["text"] == "Hello 15"
    old = client.get(f"/api/v1/conversations/{direct_id}/messages?limit=10&offset=20", headers=bob).json()
    assert [m["text"] for m in old["items"]] == [f"Hello {i}" for i in range(4, -1, -1)]
    assert old["has_more"] is False and old["next_offset"] is None

    assert client.get(f"/api/v1/conversations/{direct_id}/messages", headers=eve).status_code == 403
    assert client.post(f"/api/v1/conversations/{direct_id}/messages", headers=eve, json={"text": "intrusion"}).status_code == 403
    assert client.get("/api/v1/conversations", headers=eve).json() == []
    assert client.post(f"/api/v1/conversations/{direct_id}/messages", headers=alice, json={"text": "  "}).status_code == 422
    assert client.get(f"/api/v1/conversations/{direct_id}/messages?limit=999", headers=alice).status_code == 422


def test_uploads_text_plus_media_and_authorization(client):
    alice_id, alice = make_user(client, "alice")
    bob_id, bob = make_user(client, "bob")
    eve_id, eve = make_user(client, "eve")
    conversation_id = client.post("/api/v1/conversations", headers=alice, json={"recipient_id": bob_id}).json()["id"]

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    uploaded = client.post(
        f"/api/v1/conversations/{conversation_id}/attachments",
        headers=alice,
        files={"file": ("photo.png", BytesIO(png), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    aid = uploaded.json()["id"]
    path = f"/api/v1/media/{aid}"
    assert client.get(path, headers=alice).content == png
    assert client.get(path, headers=bob).status_code == 404  # Not yet sent
    assert client.get(path, headers=eve).status_code == 403
    assert client.get(path).status_code == 401

    sent = client.post(
        f"/api/v1/conversations/{conversation_id}/messages", headers=alice,
        json={"text": "Photo from today!", "attachment_ids": [aid]},
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["attachments"][0]["content_type"] == "image/png"
    assert client.get(path, headers=bob).content == png
    assert client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=bob,
                       json={"text": "Trying to reuse", "attachment_ids": [aid]}).status_code == 400

    # Same flow works for video, even with no text.
    mp4 = b"\x00\x00\x00\x18ftypisom" + b"1" * 60
    uploaded_video = client.post(
        f"/api/v1/conversations/{conversation_id}/attachments", headers=alice,
        files={"file": ("clip.mp4", BytesIO(mp4), "video/mp4")},
    )
    assert uploaded_video.status_code == 201, uploaded_video.text
    sent_video = client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=alice,
                             json={"attachment_ids": [uploaded_video.json()["id"]]})
    assert sent_video.status_code == 201, sent_video.text
    assert sent_video.json()["text"] == ""

    unsupported = client.post(
        f"/api/v1/conversations/{conversation_id}/attachments", headers=alice,
        files={"file": ("bad.txt", BytesIO(b"some text"), "image/png")},
    )
    assert unsupported.status_code == 415
    oversized = client.post(
        f"/api/v1/conversations/{conversation_id}/attachments", headers=alice,
        files={"file": ("huge.png", BytesIO(png + b"x" * (1024 * 1024 + 1)), "image/png")},
    )
    assert oversized.status_code == 413


def test_live_websocket_presence_and_send(client):
    alice_id, alice = make_user(client, "alice")
    bob_id, bob = make_user(client, "bob")
    direct_id = client.post("/api/v1/conversations", headers=alice, json={"recipient_id": bob_id}).json()["id"]
    alice_token = alice["Authorization"].split(" ")[1]
    bob_token = bob["Authorization"].split(" ")[1]
    socket_url = "ws://messenger.test:8080/api/v1/ws"
    browser_headers = {"Origin": "http://messenger.test:8080"}
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(
            f"{socket_url}?token={bob_token}", headers={"Origin": "http://other.test"}
        ):
            pass
    assert rejected.value.code == 1008
    with client.websocket_connect(f"{socket_url}?token={bob_token}", headers=browser_headers) as bob_ws:
        assert bob_ws.receive_json()["count"] == 1
        with client.websocket_connect(f"{socket_url}?token={alice_token}", headers=browser_headers) as alice_ws:
            assert bob_ws.receive_json()["count"] == 2
            assert alice_ws.receive_json()["count"] == 2
            online = client.get("/api/v1/users/online", headers=alice).json()
            assert online["count"] == 2 and {x["id"] for x in online["users"]} == {alice_id, bob_id}
            alice_ws.send_json({"type": "message.send", "conversation_id": direct_id, "text": "Live from my window"})
            alice_message = alice_ws.receive_json()
            bob_message = bob_ws.receive_json()
            assert alice_message["type"] == "message.new"
            assert bob_message["message"]["text"] == "Live from my window"
            assert bob_message["message"]["id"] == alice_message["message"]["id"]
        assert bob_ws.receive_json()["count"] == 1
    assert client.get("/api/v1/users/online", headers=alice).json()["count"] == 0
