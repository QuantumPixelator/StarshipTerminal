# Starship Terminal

Fast, ruthless space trading, conquest, and combat in a persistent multiplayer galaxy.

## What It Is

Starship Terminal is a client/server game where you start small, run risky trade routes, upgrade your ship, survive tactical fights, and push for system control.

- Server owns gameplay state, persistence, economy, and combat outcomes.
- Client handles rendering, UI, and audio.
- Inspired by classic BBS space trading game "Planets:TEOS" by Seth Robinson/RTSoft.

## Why Play

- High-stakes economy: market swings, contracts, and smuggling pressure every run.
- Tactical combat: bad engagements can end a streak fast.
- Planet control: hold territory, defend it, and shape the campaign outcome.
- Persistent progression: your account, ships, and world state carry forward.

## Core Gameplay

1. Buy low, move fast, sell high.
2. Upgrade for survivability and cargo efficiency.
3. Take fights you can win and avoid the ones you cannot.
4. Expand influence through standings and planet ownership.
5. Push toward campaign victory conditions.

## Quick Play

### 1) Install dependencies

```bash
py -m pip install -r requirements.txt
```

### 2) Start the server

```bash
server.bat
```

### 3) Start the client

```bash
client.bat
```

Default endpoint is `ws://localhost:8765`.

First run can take a little longer while local data initializes.

## Controls (Essential)

- `F1`: Help overlay
- `ESC`: Back/Cancel
- Orbit targeting: `W`/`S` + `ENTER`
- Orbit transfers: Arrow keys
- Mail: `N` new, `R` reply, `DELETE` remove

## Winning The Campaign

- Build credits and ship strength faster than rivals.
- Hold strategic planets consistently.
- Maintain faction momentum and avoid cascading losses.
- Survive long enough to convert economic advantage into control.

## Multiplayer Notes

- Accounts are authenticated on the server.
- Multiple characters per account are supported.
- Save data and world state are persisted in `server/saves/`.

## Where To Go Next

- Server/admin commands and setup caveats: `admin.md`
- Architecture overview: `ARCHITECTURE.md`
- Developer workflow: `DEVELOPMENT.md`
- Manual release validation: `MANUAL_VALIDATION.md`
- Complete system overview: `OVERVIEW.md`

## License

TBD
