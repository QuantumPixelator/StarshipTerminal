# StarshipTerminal Architecture

## High-Level Model
1. Server is authoritative for gameplay state, economy, combat resolution, and persistence.
2. Client handles rendering, audio playback, and local input/UI state.
3. Transport is websocket request/response actions routed by server handler maps.

## Server Flow
1. Entry point: server startup creates game server and websocket listener.
2. Session layer: authenticated player sessions map socket actions to handler functions.
3. Handler layer: modules under server/handlers parse params and call GameManager methods.
4. GameManager layer: behavior is composed from mixins in server/game_manager_modules.
5. Persistence layer: SQLiteStore in server/sqlite_store.py provides shared DB access and runtime key/value storage.

## GameManager Composition
1. Core world/player lifecycle state.
2. Economy and trading.
3. Combat and resolution.
4. Navigation and events.
5. Banking/factions/messaging/analytics helpers.

## Persistence Domains
1. Accounts and characters.
2. Runtime game state values.
3. Planet/player/combat session tables.
4. Economy resources/cargo/market tables.

## Client Flow
1. Startup: client bootstraps view stack and networking wrapper.
2. Sync layer: client/sync_network_client.py bridges sync view code to async network client.
3. Views: gameplay/map/combat/status views render using Arcade and call network actions.
4. Asset/audio: loaded and played client-side only.

## Non-Regression Guardrails
1. Never move game authority from server to client.
2. Never add server-side rendering or audio work.
3. Keep network actions defensive and explicit on validation errors.
4. Keep persistence writes safe under concurrent handler execution.
