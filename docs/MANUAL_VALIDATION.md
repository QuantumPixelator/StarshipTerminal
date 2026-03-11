# Manual Validation Checklist

This checklist covers acceptance items that cannot be fully proven by headless automated tests.

## Preconditions
1. Server starts with no tracebacks:
   - `server.bat`
2. Client starts with no tracebacks:
   - `client.bat`
3. Optional clean save state before run:
   - backup existing `server/saves/` first.

## Multiplayer Acceptance Flow (Two Clients)
1. Launch two clients and sign in as different commanders.
2. Verify both clients can reach strategic map without reconnect loops.
3. Client A travels to a new planet, then client B requests status/map refresh.
4. Confirm ownership/planet state updates are visible consistently on both clients.
5. Execute buy/sell trades on client A; verify credit/cargo changes and no desync on refresh.
6. Start combat from client A against valid target.
7. Progress at least one combat round and confirm UI updates and no hangs.
8. Verify client B remains responsive during client A combat actions.

## Persistence Acceptance
1. Perform meaningful state changes:
   - trade,
   - transfer fighters/shields,
   - optional ownership change.
2. Save and close both clients.
3. Restart server and client.
4. Sign in again and verify state persisted correctly.

## Sync Correctness Spot Checks
1. Rapidly switch between map/status/gameplay views for 2-3 minutes.
2. Confirm no stale rollback of shown state after recent actions.
3. Confirm no repeated error popups from request timeouts.

## Performance Spot Checks
1. In gameplay and combat, toggle perf HUD and verify frame pacing is stable.
2. Trigger several effects/actions quickly and confirm no sustained stutter.
3. Repeat travel + combat loop at least 5 times and check for obvious slowdown.

## Asset and Audio Checks
1. Verify ship visuals load correctly with transparent backgrounds.
2. Verify combat effects render correctly.
3. Verify expected UI/combat audio cues play; no hard errors in logs.

## Pass/Fail Criteria
1. Pass if all sections complete with no blocking defects.
2. Fail if any crash, persistent desync, data-loss-after-restart, or unrecoverable hang occurs.
3. Log each failure with steps, expected behavior, and actual behavior.
