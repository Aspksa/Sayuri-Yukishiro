# Sayuri Yukishiro

**Текущий релиз:** v0.3.0  
**Системное ядро:** v0.2.0  
**Когнитивное ядро:** v0.3.0  
**Следующая разработка:** v0.4.0

Sayuri Yukishiro — модульная персональная AI-платформа.

## Когнитивное ядро v0.3.0

Когнитивное ядро организует рабочий цикл Sayuri:

- когнитивный контекст;
- анализ намерения;
- постановка цели;
- многошаговый план;
- зависимости шагов;
- реестр способностей;
- контроль риска перед выполнением;
- квитанции и доказательства шагов;
- проверка результата;
- оценка уверенности;
- обнаружение противоречий;
- долговечное состояние сессии;
- восстановление через checkpoint и next_action;
- нейтральный ReasoningProvider для будущей LLM.

По умолчанию внешняя LLM не требуется: используется NullReasoningProvider.

Безопасность: автоматически разрешены только READ_ONLY способности. MUTATION и EXTERNAL блокируются до появления отдельного Action Broker.

Подробности: docs/COGNITIVE_CORE.md.

## Системное ядро v0.2.0

Системное ядро отвечает за:

- жизненный цикл служб;
- конфигурацию;
- журналирование;
- Event Bus;
- фоновые задачи;
- health;
- checkpoints;
- recovery;
- CoreAPI.

Подробности: docs/SYSTEM_CORE.md.

## Обязательный протокол обновлений

Каждое изменение регулируется:

- AGENTS.md
- docs/UPDATE_PROTOCOL.md
- UPDATE_IDS.json
- UPDATE_LOG.md
- PROJECT_STATE.json

Последовательность:

task -> ID -> change -> check -> version -> journal -> commit -> next_action

## Запуск

Запустите Sayuri-Yukishiro.bat.

Локальный адрес:

http://127.0.0.1:8765

## Локальный API

- GET /api/health
- GET /api/system
- GET /api/core
- GET /api/core/jobs
- GET /api/core/recovery
- GET /api/cognitive
- GET /api/cognitive/sessions
- GET /api/modules

## Хранилище

SQLite schema v3 включает системные службы, задания, checkpoints, cognitive_sessions и cognitive_receipts.

- data/core/sayuri_yukishiro.db — системное и когнитивное состояние.
- data/modules/<module_id>.db — отдельные базы будущих модулей.
- data/logs/ — журналы.
- data/cache/ — временные данные.

## Следующий этап

v0.4.0 — система модулей и их жизненный цикл. После неё реальные возможности модулей будут регистрироваться в CapabilityRegistry когнитивного ядра через контролируемые интерфейсы.
