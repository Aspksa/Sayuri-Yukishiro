# Sayuri Yukishiro

**Текущий релиз:** v0.4.0  
**Системное ядро:** v0.3.0  
**Когнитивное ядро:** v0.3.0  
**Следующая разработка:** v0.5.0

Sayuri Yukishiro — модульная персональная AI-платформа.

## Обновления проекта

Начиная с v0.4.0 обновление — часть **Системного ядра**, а не функциональный модуль.

Встроенный `UpdateService`:

- проверяет configured upstream текущей Git-ветки;
- показывает текущую и доступную версию;
- показывает список изменений;
- не изменяет проект во время preflight;
- фиксирует точный проверенный target SHA;
- не обновляет dirty или diverged worktree;
- перед применением запускает отдельный update-helper;
- мягко останавливает Sayuri;
- создаёт backup tracked-кода и SQLite;
- применяет только fast-forward к проверенному SHA;
- проверяет обновлённую версию в изолированном runtime data;
- перезапускает Sayuri только после успешных проверок;
- при сбое откатывает код и SQLite, если worktree остаётся чистым;
- блокирует destructive rollback, если после установки появились локальные изменения.

В системной web-оболочке есть страница **«Обновления проекта»** с кнопками **«Проверить»** и **«Обновить»**, прогрессом, списком изменений и журналом. Такой же пункт есть в Windows tray.

Подробная архитектура: `docs/PROJECT_UPDATES.md`.

## API обновлений

- `GET /api/update/status`
- `POST /api/update/check`
- `POST /api/update/apply`

Управляющие операции доступны только локальной системной оболочке через отдельный ephemeral control-token. UpdateService намеренно не экспортируется через обычный модульный `CoreAPI`.

## Системное ядро v0.3.0

Системное ядро управляет:

- Configuration;
- Logging;
- Event Bus;
- Job Manager;
- UpdateService;
- Checkpoints;
- Recovery;
- HealthMonitor;
- ограниченным CoreAPI.

## Когнитивное ядро v0.3.0

Когнитивное ядро содержит контекст, intent, цели, планирование, Capability Registry, Execution Gate, evidence receipts, verification, confidence, contradictions, persistence и recovery.

## Безопасность обновления

- localhost-only HTTP;
- проверка loopback client + loopback Host;
- shutdown-token и update control-token разделены;
- target SHA фиксируется на этапе проверки;
- только fast-forward apply;
- production SQLite не используется в post-update verification;
- rollback не выполняет `git reset --hard`, если worktree стал dirty;
- после restart проверяются health, identity проекта и ожидаемая версия;
- Windows PID liveness проверяется через platform-aware process utility.

## Запуск

Запустите `Sayuri-Yukishiro.bat`.

Локальный адрес: `http://127.0.0.1:8765`.

## Следующий этап

**v0.5.0 — Module Runtime & Lifecycle:** manifests, discovery, зависимости, permissions, migrations, health-check, управляемый lifecycle и безопасная регистрация способностей модулей в Cognitive CapabilityRegistry.
