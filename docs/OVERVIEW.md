# StarshipTerminal: Complete System Overview

## 1. What This Project Is

StarshipTerminal is a multiplayer, server-authoritative space trading/combat game.

- The server owns truth: player state, economy, combat outcomes, travel, persistence, and world simulation.
- The client owns presentation: rendering, UI, local effects/audio, and user input.
- Communication uses WebSocket action requests and structured JSON responses.

Repository roots:
- `server/` contains authoritative gameplay and persistence
- `client/` contains rendering, views, and networking wrapper
- `docs/` contains runbooks and architecture notes

## 2. High-Level Architecture

### 2.1 Runtime Layers

1. **Transport layer**: WebSocket request/response (`action`, `params`, `request_id`).
2. **Handler layer**: action routing in `server/handlers/*`.
3. **Domain layer**: `GameManager` mixins in `server/game_manager_modules/*`.
4. **Persistence layer**: SQLite abstractions in `server/sqlite_store.py`.
5. **Client view layer**: Arcade views in `client/views/*`.
6. **Client network layer**: async `NetworkClient` + sync bridge wrapper.

### 2.2 Authority Model

- The client can estimate and preview values (fuel cost, prices, UI timers), but the server computes and enforces actual outcomes.
- Any mutable gameplay event is confirmed by server response and snapshot sync.

## 3. Entry Points and Boot Sequence

### 3.1 Server Boot

- Entry file: `server/game_server_auth.py`
- Boot sequence:
  1. Initialize save directory and SQLite store (`server/saves/game_state.db`).
  2. Run save migrations/imports (legacy JSON migration path).
  3. Build action dispatch map using `server/handlers/__init__.py`.
  4. Start WebSocket server.

### 3.2 Client Boot

- Entry file: `client/main.py`
- View flow:
  1. `ConnectionView` (server selection)
  2. `AuthenticationView` / character selection
  3. Main gameplay views (`PlanetView`, market/travel/combat/status views)

## 4. Server Action Routing and Domains

Action dispatch is assembled in `server/handlers/__init__.py` from these modules:

- `auth_session.py`
- `player_info.py`
- `economy.py`
- `ship_ops.py`
- `navigation.py`
- `combat.py`
- `banking.py`
- `factions.py`
- `messaging.py`
- `misc.py`
- `analytics.py`
- `phase5_api.py`

Each action handler validates params and delegates to `GameManager` behavior.

## 5. GameManager Composition (Server Domain Core)

`GameManager` is composed from mixins in `server/game_manager_modules/__init__.py`:

- `CoreMixin`
- `PersistenceMixin`
- `FactionMixin`
- `EconomyMixin`
- `CrewBankMixin`
- `NavigationMixin`
- `CombatMixin`
- `ShipOpsMixin`
- `AnalyticsMixin`
- `PolishedApiMixin`

This composition is the gameplay backbone.

## 6. Persistence and Data Model (SQLite)

Primary persistence file: `server/sqlite_store.py`.

### 6.1 Important Storage Domains

- Accounts and authentication metadata
- Characters and player payloads
- Shared world state (`kv_store` namespace model)
- Strategic resources and ship cargo
- Market prices and production tables
- Combat/session/trade-offer style runtime tables

### 6.2 Key Concepts

- **`kv_store` namespaces** hold global settings and shared objects.
- **`resources`** and **`ship_cargo`** track strategic economy and per-ship inventories.
- Store writes use guarded mutation paths for concurrency safety.

## 7. Core Gameplay Systems

## 7.1 Refuel and Fuel Consumption

### Refuel path

- Server action domain: `server/handlers/ship_ops.py`
- Core logic: `ShipOpsMixin.buy_fuel` in `server/game_manager_modules/ship_ops.py`

Behavior:

1. Compute needed fuel and cost using quote/tier rules.
2. Deduct credits.
3. Increase ship fuel (capped by `max_fuel`).
4. Update `last_refuel_time`.
5. Sync persistent resource rows (`ship_cargo` + `resources`) so later consumption reads the correct amount.

### Consumption path

- Core logic: `EconomyMixin.consume_fuel` in `server/game_manager_modules/economy.py`

Behavior:

1. Read available fuel from strategic storage.
2. Apply burn amount.
3. Persist new fuel values.
4. Emit low-fuel/depleted status messages.

### Travel fuel coupling

- Travel calls fuel consumption through the server domain path.
- This coupling is strict: refuel and consume must remain storage-consistent.

## 7.2 Buy/Sell Trading Economy

Server domain: `EconomyMixin` (`server/game_manager_modules/economy.py`) and economy handlers.

Features:

- Planet market interactions for buy/sell.
- Price modifiers (planet, faction standing, event-driven multipliers, system-specific modifiers).
- Strategic resources (`fuel`, `ore`, `tech`, `bio`, `rare`) and cargo synchronization.
- Trade contract generation/rotation and rewards.
- Planet spotlight deals and dynamic economic context hooks.

## 7.3 Travel and Navigation

Server domain: `NavigationMixin` (`server/game_manager_modules/navigation.py`).

Key mechanics:

- Distance-based fuel cost (`distance`, burn rate, multipliers, crew effect).
- Travel execution with state transition to destination planet.
- Dock/undock gatekeeping and docking-fee evaluation.
- Travel event system with event payload generation and resolution.

Travel event categories include:

- Cache/salvage opportunities
- Pirates/raider encounters
- Drift/salvage decisions
- Leak/fuel-loss incidents

## 7.4 Smuggling and Contraband

Server domain: Economy + faction/security rules.

Capabilities:

- Contraband context lookup (risk/value framing).
- Detection checks with penalties.
- Heat/standing interplay.
- Bribe mechanics to alter risk dynamics and temporary conditions.

This system couples with:

- Economy pricing rules
- Faction standing outcomes
- Messaging/feedback to player

## 7.5 Combat System

Server domain: `CombatMixin` (`server/game_manager_modules/combat.py`).

Combat flow:

1. Build combat session from selected target.
2. Resolve rounds server-side (damage, statuses, effects, logs).
3. Consume combat fuel per round.
4. Finalize rewards/penalties and world-state updates.

Targets include NPC/player/planet contexts depending on mode.

### Client combat presentation

- Primary combat UI: `client/views/combat_window.py`
- Related helpers: `combat_helper.py`, effects/audio integrations

The combat UI is visual; the server owns result authority.

## 7.6 Ship Operations and Upgrades

Server domain: `ShipOpsMixin`.

Includes:

- Ship purchasing/swapping
- Hull repair
- Fighter/shield transfer operations
- Module installation from cargo
- Refuel quote and timer-window rules

## 7.7 Factions, Reputation, and Governance Pressure

Server domain: `FactionMixin` (`server/game_manager_modules/factions.py`).

Includes:

- Authority/frontier standing adjustments
- Planet access and barred checks
- Planet event overlays affecting economics and access
- Bribe-level and legal-pressure interactions

## 7.8 Banking and Crew Systems

Server domain: `CrewBankMixin` (`server/game_manager_modules/crew_bank.py`).

Includes:

- Bank deposit/withdraw and interest mechanics
- Crew payroll and activity hooks
- Crew role bonuses that influence travel/combat/economy outcomes

## 7.9 Messaging and Social Systems

Server handler domain: `server/handlers/messaging.py` and related GameManager methods.

Includes:

- Inbox/message flows
- Notifications/news style updates
- Gifting/interaction pathways tied to player entities

## 7.10 Analytics and Telemetry

Server domain: `AnalyticsMixin` + analytics handler.

Includes:

- Event recording by category
- Summaries and recommendation-style outputs
- Retention management via config

## 8. Client System Overview

## 8.1 Network Stack

### Async client

- File: `client/network_client.py`
- Responsible for:
  - WebSocket connection lifecycle
  - Request dispatch and response parsing
  - State/snapshot application
  - Cache refresh and asset sync coordination

### Sync bridge

- File: `client/sync_network_client.py`
- Provides sync-friendly calls for Arcade views while reusing async network operations.

## 8.2 Main Views and UI Surfaces

Key view files under `client/views/`:

- `connection_view.py`
- `auth_view.py`
- `gameplay.py`
- `market_view.py`
- `travel_view.py`
- `travel_event_view.py`
- `warp_view.py`
- `status_view.py`
- `combat_window.py`
- `galaxy_map_view.py`
- additional helper/secondary view modules

The view layer coordinates:

- input handling
- local prompts/modal flows
- rendering and animation
- invocation of server actions

## 8.3 Audio, Effects, and Presentation Subsystems

Files include:

- `audio_helper.py`
- `audio_playback_integration.py`
- `effects_manager.py`
- `effects_orchestrator.py`
- `particle_system.py`

Purpose:

- ambient + event SFX
- combat and travel visual effects
- UI animation support

## 8.4 Shared Client Models and Utilities

Notable client-side support files:

- `client/classes.py` (player/ship model structures)
- `client/constants.py`
- `client/components/dialogs.py`
- `client/utils/drawing.py`
- `client/utils/server_config.py`
- `client/ux_helpers.py`

## 9. End-to-End Request Flows

## 9.1 Login and Character Selection

1. Client connects and authenticates.
2. Server validates account/session.
3. Character list/select actions load persistent character payload.
4. Client receives initial world/player data and enters gameplay.

## 9.2 Buy/Sell Trade

1. Client requests market context/price data.
2. Client submits buy/sell action with quantity.
3. Server validates affordability/inventory and computes final effects.
4. Server persists state and returns success + updated snapshot.

## 9.3 Refuel

1. Client requests quote or directly buys fuel.
2. Server computes purchase and updates ship + strategic storage.
3. Subsequent travel/combat fuel consumption reads synchronized values.

## 9.4 Travel to Planet

1. Client submits target planet index/name context.
2. Server computes distance and fuel burn.
3. Server applies travel events and destination state update.
4. Optional docking step gates service access.

## 9.5 Smuggling Sale

1. Client requests contraband context.
2. Client executes sell/trade attempt.
3. Server applies detection checks and consequences.
4. Standing/credits/heat update and persist.

## 9.6 Combat Round

1. Client starts session against target.
2. Client submits per-round actions.
3. Server resolves round, applies resource changes (including fuel), and returns combat state.
4. Client renders log/effects from server result.

## 10. Config, Admin, and Operations

## 10.1 Configuration Sources

- `server/game_config.json` for baseline gameplay parameters.
- Runtime mutable settings in SQLite `kv_store`.

## 10.2 Admin and Strategic APIs

- Handler domain: `server/handlers/phase5_api.py`
- Includes campaign/admin operations such as claims, trade processing, economy ticks, and reset mechanics.

## 10.3 Asset Synchronization

- Server exports/manages manifest-backed assets.
- Client sync logic downloads updates by hash to local asset paths.

## 11. Testing and Validation Coverage

Automated tests:

- `server/tests/*`
- `client/tests/*`

Manual flows and acceptance checks:

- `docs/MANUAL_VALIDATION.md`

Developer runbook:

- `docs/DEVELOPMENT.md`

Architecture reference:

- `docs/ARCHITECTURE.md`

## 12. Important Coupling Points and Maintenance Risks

1. **Fuel synchronization**: refuel and consume paths must update/read the same storage truth.
2. **Snapshot ordering**: stale state application can visually roll back client values if versioning is bypassed.
3. **View/network timing**: fast transitions (travel/combat/refuel) require careful refresh ordering.
4. **Economic modifiers stacking**: many systems affect prices; debugging requires tracing all active multipliers.
5. **Faction and legal pressure interactions**: contraband, bribes, and event modifiers can compound quickly.
6. **Persistence migration**: schema and payload expectations must remain backward-safe.

## 13. Practical Reading Order for New Contributors

If you want full-system understanding quickly, read in this order:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. `server/game_server_auth.py`
4. `server/handlers/__init__.py` then each `server/handlers/*.py`
5. `server/game_manager_modules/__init__.py` then each mixin file
6. `server/sqlite_store.py`
7. `client/network_client.py` and `client/sync_network_client.py`
8. `client/views/gameplay.py`, `travel_view.py`, `market_view.py`, `combat_window.py`
9. Remaining client helpers/effects/audio modules

---

This file is intended as the unified deep overview of the project’s current architecture and gameplay systems (refuel, buy/sell, travel, smuggling, combat, banking, factions, messaging, analytics, admin, and persistence).
