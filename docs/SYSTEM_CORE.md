# Системное ядро Sayuri Yukishiro — v0.3.0

## Назначение

Системное ядро — привилегированный инфраструктурный слой Sayuri. Оно управляет жизненным циклом процесса и службами, которые должны оставаться доступными независимо от состояния будущих функциональных модулей.

## Службы ядра

1. Configuration — единая конфигурация.
2. Logging — структурированные журналы с ротацией.
3. Event Bus — внутренняя шина событий.
4. Job Manager — ограниченный пул фоновых задач.
5. UpdateService — проверка и подготовка безопасного обновления проекта.
6. Checkpoints — долговечные контрольные точки.
7. Recovery — восстановление контекста незавершённой работы.

Service Registry запускает службы по порядку и останавливает в обратном порядке.

## UpdateService

UpdateService находится внутри `core/`, а не в системе модулей. Это принципиальная граница полномочий: обновление может заменять код модулей и ядра, останавливать процесс и запускать внешний helper, поэтому эти операции нельзя выдавать обычным модулям через `CoreAPI`.

Основные обязанности:

- определить текущий configured upstream;
- обновить tracking-ref явным Git refspec;
- сравнить текущий HEAD с upstream;
- отказаться от обновления при dirty/diverged состоянии;
- определить доступную версию и список Git-изменений;
- сохранить состояние операции в `data/update/status.json`;
- подготовить immutable apply-plan с `before_sha` и `target_sha`;
- запустить внешний update-helper.

## Процесс применения

```text
Проверить
   ↓
UpdateService
   ↓
фиксированный target SHA
   ↓
apply-plan
   ↓
external update-helper
   ↓
мягкая остановка Sayuri
   ↓
backup code + SQLite
   ↓
fast-forward exact target SHA
   ↓
isolated verification
   ↓
restart + health/version gate
   ↓
SUCCESS
       или
rollback code + SQLite
```

Helper отделён от основного процесса, потому что работающий процесс не должен заменять файлы, из которых сам выполняется.

## Backup и rollback

Перед apply helper создаёт:

- ZIP-архив tracked-состояния `before_sha`;
- консистентные SQLite snapshots через `sqlite3.Connection.backup`;
- manifest списка production-БД.

Post-update verification использует отдельный временный `SAYURI_DATA_DIR`, поэтому тестовые миграции не касаются production data.

Если проверка/перезапуск новой версии не проходит, helper:

1. убеждается, что Git worktree всё ещё чистый;
2. откатывает tracked-код к записанному `before_sha`;
3. удаляет SQLite-БД, созданные только неудачной новой версией;
4. очищает `-wal`, `-shm`, `-journal`;
5. восстанавливает SQLite snapshots;
6. запускает предыдущую версию;
7. проверяет identity и ожидаемую версию.

Если worktree стал dirty после apply, destructive rollback блокируется, а backup сохраняется для ручного восстановления.

## HTTP API

Read/status:

- `GET /api/health`
- `GET /api/system`
- `GET /api/core`
- `GET /api/core/jobs`
- `GET /api/core/recovery`
- `GET /api/update/status`
- `GET /api/cognitive`
- `GET /api/cognitive/sessions`
- `GET /api/modules`

Управление обновлением:

- `POST /api/update/check`
- `POST /api/update/apply`

Мягкая остановка:

- `POST /api/shutdown`

HTTP-сервер привязан к `127.0.0.1`. Дополнительно проверяются loopback client и loopback Host. Управляющий token обновлений генерируется отдельно от shutdown-token.

## Windows tray

Tray содержит пункт **«Обновления проекта»**. Он запускает ту же проверку через локальный API и открывает встроенную страницу `/#updates`.

После helper-restart tray принимает новый PID только от health endpoint, который подтверждает `project = Sayuri Yukishiro`.

## Проверка процесса

Общий `process_alive` используется update lifecycle:

- Windows: `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess == STILL_ACTIVE`;
- POSIX: signal 0 с корректной обработкой отсутствия процесса и permission error.

## Checkpoints и Recovery

Незавершённые обычные задачи сохраняют `task_id`, `payload`, `next_action` и timestamps. Recovery возвращает контекст, но не повторяет произвольные действия автоматически.

## База данных

Текущая центральная SQLite schema — v3. Системные и когнитивные данные продолжают храниться в центральной БД, будущие модули получают собственные БД.

## Граница CoreAPI

Будущие функциональные модули получают ограниченный `CoreAPI` для статуса, конфигурации, событий, фоновых задач и checkpoints. Привилегированные операции UpdateService через этот API не экспортируются.
