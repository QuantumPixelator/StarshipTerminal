# Starship Terminal Admin Guide

This runbook covers practical server operation: startup, validation, caveats, and recovery checks.

## 1) Quick Ops

### Install deps

```bash
py -m pip install -r requirements.txt
```

### Start server

```bash
server.bat
```

### Start client

```bash
client.bat
```

Default endpoint: `ws://localhost:8765`.

## 2) Setup Notes

### Requirements

- Python 3.10+
- Dependencies from `requirements.txt`
- Windows: use provided `.bat` scripts

Direct run alternatives:

```bash
cd server
py game_server_auth.py
cd client
py main.py
```

## 3) Important Files

- `server/game_server_auth.py`: main authenticated server entrypoint
- `server/config.py`: server config/editor tooling
- `server/game_config.json`: gameplay and runtime settings
- `server/saves/`: account, character, and world persistence

## 4) Port / Connectivity

- Default websocket endpoint: `ws://localhost:8765`
- Controlled by `server_port` in settings/config
- If client cannot connect, verify port availability and firewall rules

Quick local port check on Windows:

```powershell
netstat -ano | findstr 8765
```

## 5) Automated Validation Commands

Run from repository root.

### Full server tests

```bash
py -m unittest discover -s server/tests -v
```

### Full client tests

```bash
py -m unittest discover -s client/tests -v
```

### Syntax compile checks

```bash
py -m py_compile server/game_server_auth.py server/game_server.py
py -m compileall -q server client
```

## 6) Manual Release Gate (Required)

Automated tests are not enough for final release confidence. Execute manual checks in `MANUAL_VALIDATION.md`:

- Two-client multiplayer flow
- Travel/trade/combat responsiveness
- Save/restart persistence verification
- Visual/audio spot checks

## 7) Admin / Operational Caveats

- Server is authoritative. Do not move game logic to client.
- Keep rendering/audio client-side only.
- Be careful with save cleanup scripts: they can permanently remove player/world state.
- Runtime SQLite artifacts may be regenerated when server starts.
- Some test paths intentionally trigger logged exceptions to verify error handling behavior.
- If tests are green but live behavior fails, prioritize manual two-client repro over more unit churn.

## 8) Safe Cleanup Examples

### Remove Python caches

```powershell
Get-ChildItem -Path . -Recurse -Directory -Force |
  Where-Object { $_.Name -in @('__pycache__', '.pytest_cache') } |
  Remove-Item -Recurse -Force
```

### Remove selected save artifacts (destructive)

```powershell
Remove-Item server/saves/*.json -Force
```

Only run destructive cleanup when you intentionally want a reset.

## 9) Troubleshooting

### Client cannot connect

- Confirm server is running.
- Confirm endpoint/port settings match.
- Check firewall and local port conflicts.

### Authentication problems

- Verify account/character files in `server/saves/`.
- Inspect server logs for account structure migration warnings.

### Tests pass but gameplay issue remains

- Run manual validation flow with two clients.
- Capture repro steps, expected behavior, actual behavior.

## 10) Admin Command Notes

Server-side admin command routing is covered in tests and supports operations such as campaign reset, forced combat, and credit grants.

- Handler module: `server/handlers/phase5_api.py`
- Command regression tests: `server/tests/test_phase5_handlers.py`

Recommended practice:

1. Run command in a controlled test account first.
2. Validate world/player side effects immediately.
3. Take a save backup before broad-impact actions.
