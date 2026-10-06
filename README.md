# Sayuri Yukishiro

Current release: v0.1.1
Development target: v0.2.0
Core foundation: v0.1.0

Sayuri Yukishiro is a modular personal AI platform.

## Mandatory update protocol

Every change is governed by AGENTS.md, docs/UPDATE_PROTOCOL.md, UPDATE_IDS.json, UPDATE_LOG.md and PROJECT_STATE.json.

Required sequence:

task -> ID -> change -> check -> version -> journal -> commit -> next_action

CI validates the protocol with:

python scripts/validate_update_protocol.py

## Launch

Run Sayuri-Yukishiro.bat.

The launcher resolves the project directory dynamically, finds Python, checks for safe fast-forward updates, runs diagnostics, starts the local core at http://127.0.0.1:8765, opens the site and remains available in the Windows notification area.

## Storage model

- data/core/sayuri_yukishiro.db — central core registry.
- data/modules/<module_id>.db — isolated storage owned by each module.
- data/logs/ — runtime logs.
- data/cache/ — disposable cache.

## Update safety

Automatic Git updates are conservative: local changes block automatic update, only origin/main is fetched, only fast-forward is accepted and divergent history is never overwritten automatically.

## Current foundation

- Portable launcher
- Windows tray host
- Diagnostics
- Local web shell
- SQLite core database
- Per-module SQLite databases
- Module registry
- Audit/event/job primitives
- Safe Git update check
- Machine-readable project state
- Mandatory version/change/bug/fix/feature/improvement/architecture IDs

## Next release after governance

The next functional release is v0.2.0 — Module Runtime & Lifecycle, because the mandatory versioning policy classifies new functionality as a MINOR release.
