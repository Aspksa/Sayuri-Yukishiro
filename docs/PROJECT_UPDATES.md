# Обновления проекта — архитектура v0.4.0

## Статус

«Обновления проекта» — встроенная функция системной оболочки Sayuri Yukishiro и служба системного ядра. Это **не модуль**.

## Почему не модуль

Обновление должно работать, даже если функциональные модули отключены или повреждены. Оно также обладает полномочиями, которых у обычного модуля быть не должно: останавливать ядро, менять tracked-файлы проекта, запускать helper, восстанавливать backup и перезапускать Sayuri.

## Компоненты

### UpdateService

`src/sayuri_yukishiro/core/update_service.py`

Работает внутри System Core. Проверяет upstream, формирует состояние и immutable apply-plan, запускает helper.

### Git inspection

`src/sayuri_yukishiro/updater.py`

Только инспектирует состояние и делает fetch tracking-ref. Самостоятельно не выполняет merge/update во время preflight.

### Update helper

`src/sayuri_yukishiro/update_helper.py`

Отдельный процесс, который переживает остановку основного ядра и выполняет backup/apply/verification/restart/rollback.

### Persistent state

`data/update/status.json`

Содержит phase, progress, версии, SHA, изменения, PID helper/restart, пути backup и журнал.

### Web shell

Встроенная страница **«Обновления проекта»** находится в системном `web/index.html`, а не поставляется модулем.

### Windows tray

Пункт **«Обновления проекта»** использует тот же API, что и web shell.

## Состояния

Основные phases:

- idle;
- checking;
- available;
- up_to_date;
- blocked;
- unavailable;
- error;
- prepared;
- waiting_for_shutdown;
- backing_up;
- applying;
- verifying;
- rolling_back;
- restarting;
- completed;
- rolled_back;
- failed.

После аварийного завершения helper UpdateService снимает stale busy-state и переводит операцию в recoverable failed.

## Инварианты безопасности

1. Apply возможен только для чистого worktree.
2. История должна быть fast-forward.
3. Применяется именно target SHA, проверенный пользователем.
4. Upstream tracking-ref обновляется явным refspec.
5. Production data не используется для post-update verification.
6. До apply создаются backup кода и SQLite snapshots.
7. Неуспешный новый процесс завершается до rollback.
8. Rollback кода разрешён только при чистом worktree.
9. Rollback SQLite восстанавливает manifest-снимок и удаляет БД/sidecars, созданные неудачной версией.
10. Restart успешен только при `status=ok`, правильной identity проекта и ожидаемой версии.
11. Update control-token отделён от shutdown-token.
12. HTTP требует loopback client и loopback Host.
13. UpdateService не экспортируется в обычный модульный CoreAPI.

## Проверки после обновления

Helper выполняет:

1. `scripts/validate_update_protocol.py`;
2. Python compileall;
3. unit/regression tests;
4. runtime preflight.

Только после их успеха запускается production runtime новой версии.

## Ручное восстановление

Если после apply появились локальные изменения, автоматический destructive rollback блокируется. В `data/update` сохраняются code archive, SQLite snapshots, apply-plan и helper log — они служат доказательствами и материалом для ручного восстановления.
