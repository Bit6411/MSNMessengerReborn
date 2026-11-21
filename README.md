# Ping! — MSN-inspired Messenger (FastAPI + SQLite)

A hackathon-ready **backend plus simple browser demo**, based on a modular FastAPI / SQLAlchemy starter. It uses **SQLite (no database server or password required)**, SQLAlchemy 2, Pydantic 2, Jinja templates, root-level static assets, REST APIs and WebSockets. **No Docker and no Alembic.**

## Features

- Register and log in with username/password. Passwords are Argon2-hashed; JWT bearer tokens authorize REST calls and WebSockets.
- Private 1:1 direct-message conversations and live events for both participants.
- A message can contain text, up to 4 images/videos, or any combination of those.
- Private files are kept on disk under `uploads/`, **not publicly mounted as static files**; the API checks conversation membership before reading them.
- Online presence: list of online users plus count, updated through WebSockets. One person with multiple tabs is counted once.
- Paginated history: `GET .../messages?limit=20&offset=0` retrieves the 20 newest messages. `offset=20` gets 20 older messages. Results are **newest first** (sort by `message.id DESC`).
- Short, persistent profile bio and a current status with Online, Idle, or Do Not Disturb availability and an optional 280-character description.
- Hover over a buddy or reach their entry with Tab to see their availability and status description.
- The legacy status-post API supports private threads linked to a specific post. Existing threads remain available in Conversations.
- Nostalgic, responsive HTML/Jinja/CSS/JS demo at `/` (not a finished production design).

## Structure

```text
msnmessenger-reborn-sqlite-starter/
├── .env                        # Your LOCAL secrets/settings; ignored by Git
├── .env.example                # Committable settings template
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
├── msnmessenger_reborn.db        # Local SQLite DB, created at startup (Git-ignored)
├── README.md
├── app/
│   ├── main.py                 # FastAPI app, CORS, static, templates, routes, startup
│   ├── api/
│   │   ├── deps.py             # get_db(), CurrentUser JWT dependency
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │           ├── auth.py
│   │           ├── users.py
│   │           ├── statuses.py
│   │           ├── conversations.py
│   │           ├── media.py
│   │           └── websocket.py
│   ├── core/
│   │   ├── config.py           # .env -> validated Settings, SQLite path/URL
│   │   └── security.py         # Argon2 passwords and JWT
│   ├── crud/
│   │   ├── conversation.py
│   │   └── message.py
│   ├── db/
│   │   ├── base.py             # SQLAlchemy DeclarativeBase
│   │   ├── session.py          # Engine and Session
│   │   └── init_db.py          # Create tables and apply local schema upgrades
│   ├── models/
│   │   ├── user.py
│   │   ├── status.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   └── attachment.py
│   ├── schemas/
│   │   ├── user.py
│   │   ├── status.py
│   │   ├── conversation.py
│   │   └── message.py
│   └── services/
│       ├── chat.py             # Publish events and WS DB sessions
│       ├── presence.py         # In-memory active socket registry
│       └── media.py            # Supported media signatures/storage path
├── templates/
│   └── index.html
├── static/
│   ├── css/app.css
│   └── js/app.js
├── uploads/                     # Private local media, not exposed as /static
│   └── .gitkeep
└── tests/
    ├── conftest.py
    └── test_messenger.py
```

## Quick start — Windows + SQLite

Use Python **3.11+**. SQLite is included in Python, so **you do not need to install MySQL, run a database server, or remember any database passwords**. Run commands in PowerShell from the extracted project root.

**1. Make your Python environment:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If activation is blocked by PowerShell, use `.venv\Scripts\python.exe -m pip install -r requirements.txt`, then `.venv\Scripts\python.exe -m uvicorn ...`.

**2. Configure `.env`:** Copy `.env.example` to `.env` to keep a stable local configuration. SQLite defaults to a file named `msnmessenger_reborn.db` in the project root:

```env
SQLITE_DB_PATH=msnmessenger_reborn.db
```

You can change the filename or use an absolute path. The app resolves relative paths against the project root, not your current working directory. Replace the **example JWT secret** with a private random value (once per installation):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the printed value into `JWT_SECRET_KEY=...` in `.env`. **Never commit `.env`**. Without a configured secret, the server generates one at startup and existing sessions expire when the process restarts.

**3. Start the server:**

```powershell
uvicorn app.main:app --reload
```

FastAPI creates `msnmessenger_reborn.db`, creates any missing tables, and upgrades older databases to support conversation end tracking and system messages. To initialize or upgrade the schema manually, run `python -m app.db.init_db`. **No `CREATE DATABASE` command is required.**

**4. Open:**

- Browser demo: http://127.0.0.1:8000/
- Interactive API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

**5. Test with two users.** Register Alice in one browser and Bob in an incognito window. Both must keep the site open for their WebSockets to count as online. Exchange live messages, then use **Edit status** under Bob's profile to set an availability and a description. Alice can look up the description using **Search by status**.

**Mac/Linux quick start**: replace `py` with `python3`, activate with `source .venv/bin/activate`, then use the same install/server commands.

## API contract

All paths below start with `/api/v1`, except `/health`, `/`, and `/static/...`. Protected API routes require `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/register` | Create user |
| `POST` | `/auth/login` | Returns JWT + user |
| `GET` | `/auth/me` | Identify authenticated user |
| `GET` | `/users?limit=50&offset=0` | Directory (excluding yourself) |
| `GET` | `/users/online` | `{count, users: [...]}` — live WebSocket users |
| `GET` | `/users/{user_id}` | Public profile and bio |
| `PATCH` | `/users/me` | Set `display_name` and/or `bio` |
| `GET` | `/users/me/status` | Get your current availability and description |
| `PUT` | `/users/me/status` | Replace your current status. Use `online`, `idle`, or `dnd` and an optional `description`. An empty description clears it. |
| `POST` | `/statuses` | Post a new status |
| `GET` | `/statuses` | Recent status feed |
| `GET` | `/users/{user_id}/statuses` | A user's statuses |
| `GET` | `/statuses/{status_id}` | Particular status |
| `POST` | `/conversations` | Get/create a normal DM or status-based DM |
| `GET` | `/conversations` | Your conversations |
| `GET` | `/conversations/{id}` | One conversation, membership required |
| `GET` | `/conversations/{id}/messages?limit=20&offset=0` | Newest page of history |
| `POST` | `/conversations/{id}/messages` | Send text/media message by REST (also pushes WS event) |
| `POST` | `/conversations/{id}/attachments` | Upload a single media file as `multipart/form-data` |
| `GET` | `/media/{attachment_id}` | Authenticated media download / inline playback |
| `WS` | `/ws?token=JWT` | Live updates and WS sends |

### Send a normal DM

```json
POST /api/v1/conversations
{"recipient_id": 2}
```

This returns conversation `id` for that pair of users, e.g. `3`.

```json
POST /api/v1/conversations/3/messages
{"text": "hey, anyone online?", "attachment_ids": []}
```

### Start a private thread from a status

Bob posts:

```json
POST /api/v1/statuses
{"text": "Does anyone want to play Snake?"}
```

Alice replies by creating a status-scoped conversation (using Bob's user ID and the status ID):

```json
POST /api/v1/conversations
{"recipient_id": 2, "status_id": 7}
```

Then Alice sends a message to the returned conversation ID. Replies happen inside **that private conversation**, with a reference to Bob's original status. Repeating this create call returns the same conversation; it does not create duplicates. A different status gets its own conversation.

### Send an image/video with text

1. Send `multipart/form-data` with field **`file`** to `POST /api/v1/conversations/3/attachments`.
2. The response contains an **attachment ID**. Repeat for additional files (max 4 per message).
3. Send a message:

```json
POST /api/v1/conversations/3/messages
{"text": "look at this 😄", "attachment_ids": [12, 13]}
```

Send `{"text":"", "attachment_ids":[12]}` for media-only. Max single file size is controlled by `MAX_UPLOAD_MB` (default 50 MB); only JPEG, PNG, GIF, WebP, MP4 and WebM are accepted. Uploads are **staged** until attached to a message. Other participants cannot view a staged attachment. Files persist locally; deletion/cleanup of abandoned uploads is a future improvement.

Media requires an Authorization header, so a custom JS frontend should `fetch(url, {headers:{Authorization: ...}})` and use a Blob URL for `<img>`/`<video>` elements. The provided browser demo does this.

### Get message history

```text
GET /api/v1/conversations/3/messages?limit=20&offset=0
GET /api/v1/conversations/3/messages?limit=20&offset=20
GET /api/v1/conversations/3/messages?limit=20&offset=40
```

Response:

```json
{
  "items": [
    {"id": 145, "conversation_id": 3, "sender_id": 1, "text": "hey", "attachments": [], "created_at": "2026-11-21T12:00:00"}
  ],
  "limit": 20,
  "offset": 0,
  "total": 145,
  "has_more": true,
  "next_offset": 20
}
```

Results are **newest first**. Reverse `items` in your UI when displaying a chronological chat transcript. Offset pagination is simple but can shift if new messages arrive while loading older pages; a cursor like `before_id` is better at scale.

### WebSocket protocol

Connect to `ws://127.0.0.1:8000/api/v1/ws?token=<JWT>` (use `wss://` with HTTPS when deployed). With an authenticated open socket you are considered online.

**Client → server** send JSON:

```json
{"type":"message.send", "conversation_id":3, "text":"hello live!", "attachment_ids":[]}
```

**Server → both conversation participants**:

```json
{"type":"message.new", "message": {"id":146,"conversation_id":3,"sender_id":1,"text":"hello live!","attachments":[],"created_at":"2026-11-21T12:01:00"}}
```

**Server → online users, on connection/disconnection**:

```json
{"type":"presence.update", "count":2, "user_ids":[1,2]}
```

**Server → sender, on invalid WS message**:

```json
{"type":"message.error", "detail":"Invalid message or attachment"}
```

A REST `POST /messages` also saves to the database **and** publishes the `message.new` event to connected participants, so a frontend may choose REST or WebSockets for sending.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
pytest -q
```

Automated tests use an in-memory SQLite database and override the normal file-based SQLite session and WebSocket session factories. They cover registration, login, profile update, statuses, ordinary DM vs. status thread, offset pagination, private media access, image/video messages, and actual WebSocket messaging/presence. **A file-backed SQLite smoke test is also recommended before deployment.**

## Design decisions / limitations

- **Explicit schema upgrades:** `Base.metadata.create_all()` creates missing tables. Changes to existing tables need an explicit upgrade in `app/db/init_db.py`.
- **SQLite is local-only:** the `msnmessenger_reborn.db` file (plus optional `-wal`/`-shm` sidecar files) is local application state. Do not commit it. For higher write concurrency or multi-server deployment, migrate to a server database (such as PostgreSQL). SQLite foreign keys and WAL mode are enabled for the app engine.
- **One server process:** presence and broadcast connections are stored in Python memory (`services/presence.py`). Use `uvicorn app.main:app --reload` with one worker for development. A multi-instance production system needs Redis pub/sub or another shared presence/event bus.
- **Basic dev security only:** change the example JWT secret, use HTTPS/WSS and secure HttpOnly cookie/session auth for a public deployment, configure strict allowed origins, set web-server request-size limits, add rate limiting and upload scanning/transcoding, and implement password resets/account recovery. The local browser demo stores the JWT in `sessionStorage`; this is not the preferred production token-storage method. WebSocket token-in-query is a browser-friendly **local prototype compromise** and can leak via URL logs.
- **No read receipts, typing indicator, status edit/delete, image resizing, voice/video calls, push notifications, or shared desktop yet.** These can come later.
- No built-in friendship system: authenticated users can list other accounts and start a DM. Add friend requests/blocking/privacy controls before opening the service publicly.

## Suggested next build steps

Make the UI more recognizably MSN: movable chat windows, custom avatars, nudge animation, presence sounds and away/busy states. Then add the shared-desktop concept as a separate entity keyed to a conversation, containing notes/widgets that sync via the same WebSocket infrastructure.
