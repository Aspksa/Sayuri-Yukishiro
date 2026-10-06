# Sayuri Yukishiro — журнал обновлений

Журнал ведётся по docs/UPDATE_PROTOCOL.md. ID никогда не сбрасываются.

---

## v0.1.0

Дата: 2026-10-07

Статус: completed

Изменения:

- CHG-0001 / ARCH-0001 — заложено разделение launcher, core runtime, storage и модульных БД.
- CHG-0002 / FEAT-0001 — добавлен переносимый Sayuri-Yukishiro.bat, диагностика и Windows tray.
- CHG-0003 / FEAT-0002 — добавлена центральная SQLite-база и отдельное хранилище БД модулей.
- CHG-0004 / FEAT-0003 — добавлено безопасное GitHub-обновление только fast-forward при чистом worktree.
- CHG-0005 / FEAT-0004 — добавлен локальный web shell и health/system/module API.
- CHG-0006 / BUG-0001 — обнаружено смешивание вывода PowerShell preflight с кодом возврата.
- CHG-0007 / FIX-0001 -> BUG-0001 — код возврата preflight отделён от пользовательского вывода.
- CHG-0008 / BUG-0002 — обнаружено подавление видимого вывода диагностики через Out-Null.
- CHG-0009 / FIX-0002 -> BUG-0002 — восстановлен видимый диагностический отчёт при BAT-запуске.
- CHG-0010 / FEAT-0005 — добавлен GitHub Actions Foundation Smoke.
- CHG-0011 / BUG-0003 — CI обнаружил незакрытый SQLite file handle на Windows.
- CHG-0012 / FIX-0003 -> BUG-0003 — введён явный lifecycle SQLite open -> transaction -> close.

Проверки:

- tests: PASS
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PASS
- python-compile: PASS
- powershell-syntax: PASS

Commit:

a98ae9a3f7c87967fcce7912122a96317e3ecde0
c515390d7e7e7568c21baceab2d4b48a1f89bc3b
14e9df2fdeed20c1a3f608b48eb4f4dd006660ae
251aae0ac99db9fa7e6d7a8b7775372823e2687f
803e2af214f9f460d1d0418209296322141e7260

Следующий шаг:

next_action: v0.1.1 — внедрить обязательный протокол обновлений и машинную проверку ID.

---

## v0.1.1

Дата: 2026-10-07

Статус: completed

Изменения:

- CHG-0013 / ARCH-0002 — протокол обновлений превращён в обязательное правило репозитория и добавлен AGENTS.md.
- CHG-0014 / FEAT-0006 — добавлены машинный реестр ID и валидатор протокола.
- CHG-0015 / IMP-0001 — протокол интегрируется с PROJECT_STATE.json, README и GitHub Actions.
- CHG-0016 / BUG-0004 — CI обнаружил переэкранированные regex в валидаторе, из-за чего ID не распознавались.
- CHG-0017 / FIX-0004 -> BUG-0004 — regex валидатора исправлены до корректных raw-паттернов Python.
- CHG-0018 / BUG-0005 — валидатор ошибочно считал обязательную ссылку FIX -> BUG повторным объявлением BUG-ID.
- CHG-0019 / FIX-0005 -> BUG-0005 — уникальность ID теперь проверяется по первичным объявлениям, а FIX-ссылки валидируются отдельно.

Проверки:

- tests: PASS
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PASS
- protocol-validation: PASS
- python-compile: PASS
- powershell-syntax: PASS

Commit:

3b7c54c23883300e8de6335f5b96e4fd40ebf231

Следующий шаг:

next_action: v0.2.0 — Module Runtime & Lifecycle: manifests, discovery, dependencies, permissions, migrations, health checks and controlled startup/shutdown.


---

## v0.2.0

Дата: 2026-10-07

Статус: completed

Изменения:

- CHG-0020 / ARCH-0003 — системное ядро выделено в отдельный слой между запуском проекта и будущими модулями.
- CHG-0021 / FEAT-0007 — добавлены реестр служб и управляемый жизненный цикл служб ядра.
- CHG-0022 / FEAT-0008 — добавлена внутренняя шина событий ядра с изоляцией ошибок обработчиков.
- CHG-0023 / FEAT-0009 — добавлен диспетчер фоновых задач с фиксацией прерванных задач после перезапуска.
- CHG-0024 / FEAT-0010 — добавлена единая служба конфигурации с локальным JSON и безопасными переменными окружения.
- CHG-0025 / FEAT-0011 — добавлено структурированное журналирование ядра с ротацией файлов.
- CHG-0026 / FEAT-0012 — добавлен контроль состояния служб и агрегированная диагностика ядра.
- CHG-0027 / FEAT-0013 — добавлены долговечные контрольные точки задач с payload и next_action.
- CHG-0028 / FEAT-0014 — добавлено безопасное восстановление незавершённой работы после перезапуска без автоматического повторения произвольных действий.
- CHG-0029 / ARCH-0004 — введён ограниченный CoreAPI как единый интерфейс системного ядра для будущих модулей.
- CHG-0030 / IMP-0002 — диагностика и HTTP API расширены состоянием ядра, заданиями и восстанавливаемыми задачами.

Проверки:

- tests: PASS
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PASS
- protocol-validation: PASS
- python-compile: PASS
- powershell-syntax: PASS

Commit:

4273915d7938d7b741612c379a03ff09e2c84e04

Следующий шаг:

next_action: v0.3.0 — Система модулей и их жизненный цикл: manifest, обнаружение, зависимости, разрешения, миграции, health-check и управляемый запуск/остановка модулей.


---

## v0.3.0

Дата: 2026-10-07

Статус: completed

Изменения:

- CHG-0031 / ARCH-0005 — когнитивное ядро выделено в отдельный слой над системным ядром.
- CHG-0032 / FEAT-0015 — добавлены рабочий когнитивный контекст и долговечные сессии задач.
- CHG-0033 / FEAT-0016 — добавлен детерминированный анализатор намерения пользователя.
- CHG-0034 / FEAT-0017 — добавлена постановка целей с критериями успеха и обязательными ограничениями безопасности.
- CHG-0035 / FEAT-0018 — добавлен планировщик многошаговых задач с зависимостями шагов.
- CHG-0036 / FEAT-0019 — добавлены реестр способностей и ExecutionGate; MUTATION/EXTERNAL блокируются до будущего Action Broker.
- CHG-0037 / FEAT-0020 — добавлены долговечные ExecutionReceipt с доказательствами выполнения каждого шага.
- CHG-0038 / FEAT-0021 — добавлен ResultVerifier с контролем завершённости, blocked/failed/pending шагов.
- CHG-0039 / FEAT-0022 — добавлены техническая оценка уверенности и обнаружение противоречивых ограничений.
- CHG-0040 / FEAT-0023 — когнитивные сессии связаны с checkpoint/recovery системного ядра и сохраняют точный next_action.
- CHG-0041 / FEAT-0024 — реализован единый CognitiveCore цикл: контекст -> намерение -> цель -> план -> capability -> evidence -> verification -> checkpoint.
- CHG-0042 / FEAT-0025 — добавлен нейтральный ReasoningProvider и NullReasoningProvider для работы без обязательной внешней LLM.
- CHG-0043 / ARCH-0006 — SQLite расширен схемой v3 с cognitive_sessions и cognitive_receipts.
- CHG-0044 / IMP-0003 — диагностика и локальный read-only API расширены /api/cognitive и /api/cognitive/sessions.
- CHG-0045 / BUG-0006 — CI обнаружил недетерминированный порядок квитанций шагов при одинаковом времени записи.
- CHG-0046 / FIX-0006 -> BUG-0006 — порядок квитанций закреплён по порядку вставки SQLite, timestamp повышен до микросекунд.

Проверки:

- tests: PASS
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PASS
- protocol-validation: PASS
- python-compile: PASS
- powershell-syntax: PASS

Commit:

4fd967b5f78a5461f671e019649882df36bfc9de

Следующий шаг:

next_action: v0.4.0 — Система модулей и их жизненный цикл: manifests, discovery, dependency graph, permissions, migrations, health-check и управляемый запуск/остановка; затем подключить реальные способности модулей к когнитивному CapabilityRegistry.
