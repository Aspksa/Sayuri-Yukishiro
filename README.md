# Sayuri Yukishiro

**Project version:** 0.1.0  
**Core foundation:** 0.1.0

Sayuri Yukishiro is a modular personal AI platform. Version 0.1.0 establishes the portable Windows runtime, core database layer, diagnostics, local web shell, tray launcher, and safe GitHub update path.

## Launch

Run:

```text
Sayuri-Yukishiro.bat
```

The launcher:

1. Resolves the project directory dynamically, so no fixed drive letter is required.
2. Finds Python in `runtime\python`, `.venv`, PATH, or the Windows `py` launcher.
3. Checks for a safe Git fast-forward update from `origin/main`.
4. Runs diagnostics and initializes SQLite.
5. Starts the local core at `http://127.0.0.1:8765`.
6. Opens the site in the default browser.
7. Keeps Sayuri in the Windows notification area (system tray) with Open, Diagnostics, Restart, and Exit actions.

## Storage model

- `data/core/sayuri_yukishiro.db` — central core registry.
- `data/modules/<module_id>.db` — isolated storage owned by each module.
- `data/logs/` — runtime logs.
- `data/cache/` — disposable cache.

The core registry contains module metadata, settings, events, jobs, audit records, and schema migration state.

## Update safety

Automatic update is intentionally conservative:

- only a Git working copy is updated;
- local changes stop automatic update;
- only fast-forward updates from `origin/main` are accepted;
- divergent history is never overwritten automatically.

Portable release-package updating can be added later without weakening this safety model.

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

See `PROJECT_STATE.json` and `docs/ARCHITECTURE.md`.

## Next release

**v0.1.1 — Module Runtime & Lifecycle**

Manifests, module discovery, dependency checks, permissions, module migrations, health state, startup/shutdown lifecycle, and isolated module APIs.
