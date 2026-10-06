# Sayuri Yukishiro Architecture — v0.1.0

## 1. Foundation

Version 0.1.0 is the platform foundation. It intentionally separates the launcher, core runtime, storage, modules, and web interface so future features can evolve independently.

```text
Sayuri-Yukishiro.bat
        |
        v
scripts/launcher.ps1
        |
        +--> preflight diagnostics
        +--> safe Git update
        +--> Python core process
        +--> browser
        +--> Windows tray
                 |
                 v
src/sayuri_yukishiro/
        |
        +--> diagnostics
        +--> updater
        +--> database
        +--> local HTTP core
                 |
                 +--> web/
                 +--> data/core/
                 +--> data/modules/
```

## 2. Portable path rule

No component may assume a fixed drive letter or installation directory. Paths derive from the repository/project root. Moving the whole directory from one writable Windows volume to another must not require configuration changes.

## 3. Database rule

The project uses a two-level SQLite model.

### Core database

`data/core/sayuri_yukishiro.db`

Responsibilities:

- registered modules;
- global and scoped settings;
- event stream;
- background job state;
- audit trail;
- schema migration ledger.

### Module databases

`data/modules/<module_id>.db`

A module owns its tables and migrations. Cross-module data exchange should go through defined core/module APIs instead of direct table coupling.

This keeps large future modules such as Memory, DNA, Laboratory, Projects, or integrations independently maintainable.

## 4. Launcher and tray

The BAT file is the only entry point a normal Windows user needs. PowerShell is used as the tray host because Windows already provides it, avoiding a GUI dependency merely to show a notification-area icon.

The tray exposes:

- Open Sayuri
- Diagnostics
- Restart core
- Exit

## 5. Web exposure

The initial server binds to `127.0.0.1` only. It is not exposed to the LAN or Internet by default.

## 6. Automatic updates

v0.1.0 supports safe Git working-copy updates:

1. Verify Git is available and this directory is a worktree.
2. Refuse automatic update when local changes exist.
3. Fetch `origin/main`.
4. Update only when the current commit is an ancestor of `origin/main`.
5. Use fast-forward only.
6. Never run reset/force checkout automatically.

## 7. Versioning

Project releases use SemVer. Every released change increments the project version. Modules also have their own version, allowing a module to evolve without hiding its compatibility state.

## 8. Next architectural layer

v0.1.1 will introduce Module Runtime & Lifecycle:

- manifest format;
- module discovery;
- enable/disable state;
- dependency resolution;
- permissions/capabilities;
- migrations;
- health checks;
- controlled startup/shutdown;
- API routing;
- module version compatibility.
