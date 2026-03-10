# datacloud-agent-service

FastAPI Gateway Service Layer for OpenClaw.

## Development

```bash
# Install dependencies
uv sync

# Run the service
uv run python -m server

# Run tests
pytest
```

## Quick Start Scripts

The `scripts/` directory contains convenience scripts for running the service.

### Start Service Only

```bash
./scripts/start.sh
```

Environment variables:
- `DATACLOUD_SERVICE_HOST` - Server host (default: 0.0.0.0)
- `DATACLOUD_SERVICE_PORT` - Server port (default: 8000)
- `DATACLOUD_SERVICE_RELOAD` - Enable auto-reload (default: false)

### Start Service with UI

```bash
./scripts/start_with_ui.sh
```

Environment variables:
- `DATACLOUD_SERVICE_HOST` - Service host (default: 0.0.0.0)
- `DATACLOUD_SERVICE_PORT` - Service port (default: 8000)
- `DATACLOUD_UI_PORT` - UI port (default: 3000)

This will start both the FastAPI backend and the Next.js dev server for the UI.
