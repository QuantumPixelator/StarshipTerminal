# StarshipTerminal Development Runbook

## Local Setup
1. Install dependencies:
   - py -m pip install -r requirements.txt
2. Start server from repo root:
   - server.bat
3. Start client from repo root:
   - client.bat

## Running Tests
1. Full server suite:
   - py -m unittest discover -s server/tests -v
2. Compile smoke:
   - py -m compileall -q server client

## Adding a New Server Handler
1. Add/extend function(s) in a module under server/handlers.
2. Return structured response dicts with success/error fields.
3. Validate required params and types before invoking GameManager.
4. Register action in that handler module register() map.
5. Ensure the module is included by server/handlers/__init__.py registration.
6. Add tests under server/tests for success and invalid input paths.

## Adding a New GameManager Capability
1. Implement behavior in the appropriate mixin under server/game_manager_modules.
2. Keep business rules server-authoritative.
3. Keep methods deterministic and persistence-safe.
4. Add tests that verify state changes in store and responses in handlers.

## Persistence Safety Rules
1. Use SQLiteStore helpers for DB access instead of ad hoc SQL in handlers.
2. Prefer atomic DB updates for counters/resources.
3. Treat all persisted JSON decode as untrusted and use safe fallbacks.

## Debugging Checklist
1. Reproduce with one action at a time and capture request params.
2. Confirm handler-level validation response.
3. Confirm GameManager result and persistence write.
4. Re-run targeted test and full server suite.

## Pull Request Checklist
1. Compile checks pass for touched files.
2. Relevant tests added and passing.
3. No dead code leftovers for replaced logic.
4. README/developer docs updated if commands or workflows changed.
