# Sayuri Yukishiro

**Текущий релиз:** v0.3.1  
**Системное ядро:** v0.2.1  
**Когнитивное ядро:** v0.3.0  
**Следующая разработка:** v0.4.0

Sayuri Yukishiro — модульная персональная AI-платформа.

## Стабилизация v0.3.1

- BAT больше не передаёт опасный путь `%~dp0` через `-Root`.
- Ошибка bind корректно останавливает системное и когнитивное ядра.
- Windows tray сначала выполняет мягкое завершение через токенизированный `POST /api/shutdown`; принудительный Kill — только fallback.
- SQLite использует `DELETE` на OneDrive, сетевых и съёмных путях и `WAL` на безопасном локальном диске.
- Runtime data можно вынести через `SAYURI_DATA_DIR`.
- JobManager ограничивает историю и освобождает завершённые futures.
- `/api/health` больше не запускает `quick_check` на каждом polling.
- Git updater следует upstream текущей ветки вместо жёсткого `origin/main`.
- Версия интерфейса читается из `VERSION`, Python metadata централизована в `version.py`.
- PowerShell launcher не использует автоматическую переменную `$args`.

## Когнитивное ядро v0.3.0

Контекст, намерение, цели, планирование, Capability Registry, Execution Gate, evidence receipts, verification, confidence, contradictions, persistence и recovery.

## Системное ядро v0.2.1

Lifecycle служб, конфигурация, logging, Event Bus, фоновые задачи, health, checkpoints, recovery и CoreAPI.

## Запуск

Запустите `Sayuri-Yukishiro.bat`.

Локальный адрес: `http://127.0.0.1:8765`.

## Следующий этап

v0.4.0 — система модулей и их жизненный цикл.
