# AutoHeal Enterprise

AutoHeal Enterprise monitors Docker container logs, classifies detected failures with Gemini, and routes proposed remediations through a safety gate before execution. A React dashboard exposes container status, incidents, actions, metrics, and human approval requests.

## How It Works

1. `log_monitor/monitor.py` streams logs from running containers and emits detected failures as newline-delimited JSON (NDJSON).
2. `ai_engine/decision_engine.py` redacts sensitive values, asks Gemini for a remediation decision, and emits a validated decision as NDJSON.
3. `executor/executor.py` evaluates each decision. GREEN decisions execute, YELLOW decisions wait in the approval queue, and RED decisions are blocked.
4. The FastAPI service reads the executor's JSONL audit and approval files for the React dashboard.

The executor can perform Docker actions. Run it only against containers and Docker environments you are authorized to administer.

## Project Structure

```text
.
├── ai_engine/                   # Gemini decisions, prompt building, sanitization
│   └── tests/
├── api_dashboard/
│   ├── backend/                 # FastAPI endpoints and JSONL readers
│   └── frontend/                # React dashboard
│       └── src/components/
├── executor/                    # Safety gate, Docker actions, audit logging
│   └── tests/
├── log_monitor/                 # Docker log streaming and failure detection
│   ├── injectors/               # Demo failure injectors
│   └── tests/
├── test_environment/            # Demo app, Nginx, and Compose configuration
├── SYNOPSIS/
├── approval_queue.jsonl         # Pending human approvals
├── audit_log.jsonl              # Executor audit records
└── viewer.py                    # Local log viewer
```

## Prerequisites

- Python 3.10 or newer
- Node.js and npm
- Docker Engine with the Docker daemon running and accessible to your user
- A Gemini API key for AI-driven decisions

## Setup

From the repository root, create and activate a virtual environment, then install the Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install \
  -r ai_engine/requirements.txt \
  -r executor/requirements.txt \
  -r log_monitor/requirements.txt \
  -r api_dashboard/backend/requirements.txt
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

Create a `.env` file in the repository root:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
```

Keep this key private. The `.env` file is git-ignored; do not commit credentials or paste them into logs or documentation.

Install the dashboard dependencies:

```bash
npm --prefix api_dashboard/frontend ci
```

## Run the Demo Environment

The demo application and its supporting services are defined in `test_environment/docker-compose.yml`:

```bash
docker compose -f test_environment/docker-compose.yml up --build -d
```

This starts the demo app, PostgreSQL, and Nginx. To stop them:

```bash
docker compose -f test_environment/docker-compose.yml down
```

## Run the Auto-Healing Pipeline

From the repository root, with Docker available and the `.env` file configured:

```bash
python log_monitor/monitor.py | \
  python ai_engine/decision_engine.py | \
  python executor/executor.py
```

The monitor and executor need access to the Docker daemon. The AI engine sends sanitized log events to Gemini. The pipeline runs continuously until interrupted with Ctrl+C. Its standard output is NDJSON; status messages are written to standard error. The executor appends audit records to `audit_log.jsonl` and approvals requiring review to `approval_queue.jsonl`.

To generate a connection-refused log event in the demo app, use a second terminal:

```bash
python log_monitor/injectors/inject_connrefused.py --container autoheal_app
```

The injector writes into the target container's logs. Other failure injectors are available in `log_monitor/injectors/`.

## Run the Dashboard

Start the API from its backend directory:

```bash
cd api_dashboard/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, start the frontend:

```bash
cd api_dashboard/frontend
npm start
```

Open <http://localhost:3000>. The API is available at <http://localhost:8000>; its health endpoint is `/health` and interactive API documentation is at `/docs`. The frontend defaults to `http://localhost:8000`; set `REACT_APP_API_URL` before starting it to use a different API URL.

The dashboard reads the root-level `audit_log.jsonl` and `approval_queue.jsonl` files. You can override their locations for the API with `AUTOHEAL_AUDIT_LOG` and `AUTOHEAL_APPROVAL_QUEUE`.

## Tests

Run the Python test suites from the repository root:

```bash
python -m pytest ai_engine/tests
python -m pytest executor/tests
python -m pytest log_monitor/tests
```

## Safety Model

- **GREEN:** the executor runs the permitted action automatically.
- **YELLOW:** the action is placed in the approval queue for an operator.
- **RED:** the action is rejected and not executed.

Actions are restricted by the executor's whitelist and confidence/severity rules. Treat AI output as an untrusted recommendation; the executor's safety gate determines whether it may run.
