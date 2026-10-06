# Sayuri Yukishiro

**Текущий релиз:** v0.4.0  
**Системное ядро:** v0.3.0  
**Когнитивное ядро:** v0.3.1  
**Module Runtime:** v0.4.0  
**Следующая разработка:** v0.5.0

Sayuri Yukishiro — модульная персональная AI-платформа.

## Module Runtime v0.4.0

Слой модулей между системным и когнитивным ядром. Подробности: `docs/MODULE_RUNTIME.md`.

- манифест `module.json` со строгой валидацией полей, SemVer и объявленных способностей;
- обнаружение модулей в `modules/` с изоляцией ошибок отдельного манифеста;
- граф зависимостей: детерминированный порядок запуска, циклы, отсутствующие, отключённые и несовместимые по версии зависимости;
- разрешения: чтение и собственная БД выдаются автоматически, процессы, сеть и запись в файловую систему заблокированы до Action Broker;
- миграции модульных БД с реестром применённых версий и защитой «БД новее кода»;
- жизненный цикл load -> migrate -> start -> health -> stop; по умолчанию сбой изолируется с блокировкой зависимых модулей и checkpoint с `next_action`, в строгом режиме выполняется полный откат;
- способности модулей регистрируются в когнитивном `CapabilityRegistry` как `module.<id>.<name>` и снимаются при остановке;
- эталонный модуль `modules/system_probe`;
- `/api/modules/runtime`, `/api/modules/health`, `/api/modules/states` и проверка `module_runtime` в диагностике.

## Когнитивное ядро v0.3.1

Контекст, намерение, цели, планирование, Capability Registry, Execution Gate, evidence receipts, verification, confidence, contradictions, persistence и recovery. Реестр способностей поддерживает регистрацию и снятие способностей модулей.

## Системное ядро v0.3.0

Lifecycle служб, конфигурация, logging, Event Bus, фоновые задачи, health, checkpoints, recovery и CoreAPI. Схема SQLite v4 хранит состояния модулей.

## Граница безопасности

Автоматически выполняются только способности уровня READ_ONLY. Любая MUTATION или EXTERNAL блокируется с причиной `requires_action_broker`.

## Запуск

Запустите `Sayuri-Yukishiro.bat`.

Локальный адрес: `http://127.0.0.1:8765`.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `SAYURI_PORT` | порт локального сервера |
| `SAYURI_DATA_DIR` | каталог runtime-данных |
| `SAYURI_MODULES_DIR` | дополнительные каталоги модулей |
| `SAYURI_MODULES_STRICT_STARTUP` | строгий запуск модулей с полным откатом |
| `SAYURI_SQLITE_JOURNAL_MODE` | режим журнала SQLite: `WAL` или `DELETE` |
| `SAYURI_SHUTDOWN_TOKEN` | токен мягкого завершения через `POST /api/shutdown` |

## Протокол обновлений

Любое изменение проекта обязано следовать `docs/UPDATE_PROTOCOL.md` и начинаться с чтения `AGENTS.md`, `UPDATE_IDS.json`, `UPDATE_LOG.md` и `PROJECT_STATE.json`.

Проверка протокола: `python scripts/validate_update_protocol.py`.

## Следующий этап

v0.5.0 — Action Broker: подтверждение и безопасное выполнение способностей уровня MUTATION и EXTERNAL.
