# Starship Terminal

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Retro-inspired space trading and combat game with a multiplayer client/server architecture.
- Built with love and AI (and many curse words).
- The game is loosely based on the 1990s BBS door game PLANETS:TEOS by RTSoft.
- The game is 100% playable and winnable. Detailed configuration app included (server\config.py).

## TODO
- Add more sound effects.

## What this repository contains

- `client/` - Arcade-based game client (UI, rendering, input, and server connection flow).
- `server/` - Authoritative game logic, persistence, account authentication, and config editor.
- `server/saves/` - Universe and player/account save data.
- `LICENSE` - MIT license for this project.

## Quick start

### 1) Install dependencies

Server:

```bash
py -m pip install -r requirements.txt
```

### 2) Start the server

From the repository root:

```bash
server.bat
```

or directly:

```bash
cd server
py game_server_auth.py
```

Default server endpoint: `ws://localhost:8765` (controlled by `settings.server_port` in `server/game_config.json`, editable in `server/config.py`).

### 3) Start the client

From the repository root:

```bash
client.bat
```

or directly:

```bash
cd client
py main.py
```

## Gameplay Features

- **Trading & Economy**: Buy/sell goods at planet markets with dynamic pricing, contracts, and smuggling mechanics
- **Combat System**: Tactical space combat against NPCs, players, and planetary defenses
- **Planet Ownership**: Claim and defend planets, transfer fighters/shields between ship and owned planets
- **Banking**: Deposit/withdraw credits on planets with banking services (configurable via `enable_bank`)
- **Repairs**: Hull repair available on all planets with banks, with costs scaling by ship level
- **Travel Events**: Random events during warp travel (pirates, salvage, etc.)
- **Smuggling**: Contraband trade with detection risks and bribery systems
- **Multiplayer**: Account-based authentication with multiple characters per account
- **Special Weapons**: Server-authoritative special weapon actions are available (configurable cooldowns and damage multipliers)
- **Server-side Validation**: Account and character creation include server-side validation (duplicate commander/character names are rejected server-side)
- **Modular Ship Slots**: Ships expose hardware `module_slots` and `installed_modules` (examples: `jammer`, `scanner`, `cargo_optimizer`) which provide gameplay bonuses
- **Campaign Victory & Reset**: Configurable faction + planet ownership win checks, global winner announcement mail/news, and scheduled campaign reset
- **Winner Board**: Main menu board showing historical winners and campaign outcomes
- **Systems Intelligence**: In SYSTEMS, view owned planets and open a full commander status board

## Controls

### General
- **F1**: Toggle help overlay
- **ESC**: Back/cancel

### Orbit Mode
- **W/S**: Select orbital targets
- **ENTER**: Engage selected target
- **Q/E**: Select cargo items to give (←/→ in updated version)
- **A/D/Z/X**: Transfer fighters/shields (←/→/↑/↓ in updated version)

### Owned Planet Transfers
- **←**: Leave fighters on planet
- **→**: Take fighters from planet  
- **↑**: Assign shields to planet
- **↓**: Take shields from planet

### Mail System
- **←/→**: Select messages
- **N**: Compose new message
- **R**: Reply to selected message
- **DELETE**: Remove message

### Systems Menu
- Repair button appears when ship is damaged and planet has banking services
- **L**: Open Commander Status Board (scroll with mouse wheel or keyboard)

## Configuration editor

Run the server config editor:

```bash
cd server
py config.py
```

This editor manages:

- Core gameplay settings from `server/game_config.json`
- Server listen port (`server_port`, default `8765`)
- Victory/reset controls (`victory_planet_ownership_pct`, faction commander bounds, `victory_reset_days`)
- Admin campaign reset action (double-confirmed `RESET CURRENT GAME`)
- Planet/item/spaceship content in `server/assets/texts/`
- Player/account save administration in `server/saves/`

## Validation and smoke tests

Use these commands from repository root for a broad health check.

### 1) Run extensive automated tests

```bash
py -m pytest server/tests client/tests client/views/test_effects_system.py client/views/test_gameplay_refactoring.py client/views/test_integration_phase2.py -q
```

Expected: full pass (current baseline in this repo is 202 passing tests).

### 2) Compile all Python files (syntax smoke)

```bash
py -m compileall -q server client
```

Expected: no compile errors.

### 3) Runtime bootstrap smoke test (server core)

```bash
py -c "import sys;sys.path.insert(0,'server');import planets,classes,game_manager;ps=planets.generate_planets();ss=classes.load_spaceships();gm=game_manager.GameManager();print(f'smoke_ok={len(ps)>0 and len(ss)>0 and len(gm.planets)>0} planets={len(ps)} ships={len(ss)} gm_planets={len(gm.planets)}')"
```

Expected: `smoke_ok=True` and non-zero counts.

### 4) Optional targeted server regression run

```bash
py -m pytest server/tests/test_modules.py server/tests/test_server_handlers.py -q
```

Expected: all pass.

### 5) Cleanup generated cache artifacts

PowerShell:

```powershell
Get-ChildItem -Path . -Recurse -Directory -Force | Where-Object { $_.Name -in @('__pycache__','.pytest_cache') } | Remove-Item -Recurse -Force
```

Notes:
- Some Windows environments may print transient Arcade/Pyglet graphics initialization noise during import-smoke collection while still completing tests successfully.
- GUI interaction paths (full gameplay loop, dialogs, rendering) should still be manually spot-checked by running server + client.

## Server capacity

- Concurrent player capacity is primarily limited by host resources (RAM, CPU, disk I/O, and network bandwidth).
- Practical RAM estimate: plan for about **20-60 MB per logged-in account session** (depends on save size, active systems, and runtime overhead).
- For stable hosting, leave additional headroom for Python, OS services, and burst activity.


## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
