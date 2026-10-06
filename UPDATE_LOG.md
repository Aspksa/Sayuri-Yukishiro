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


---

## v0.3.1

Дата: 2026-10-07

Статус: completed

Изменения:

- CHG-0047 / BUG-0007 — BAT передавал -Root "%~dp0", что создавало риск некорректного разбора завершающего обратного слэша.
- CHG-0048 / FIX-0007 -> BUG-0007 — BAT больше не передаёт Root; launcher вычисляет корень через PSScriptRoot.
- CHG-0049 / BUG-0008 — при ошибке bind HTTP-порта запущенные ядра могли остаться без stop().
- CHG-0050 / FIX-0008 -> BUG-0008 — serve() гарантированно закрывает сервер, когнитивное и системное ядра через finally.
- CHG-0051 / BUG-0009 — tray завершал Python через Kill(), обходя штатный lifecycle.
- CHG-0052 / FIX-0009 -> BUG-0009 — добавлен локальный токенизированный POST /api/shutdown; Kill используется только как аварийный fallback после таймаута.
- CHG-0053 / BUG-0010 — SQLite WAL включался без учёта OneDrive, сетевых и съёмных путей.
- CHG-0054 / FIX-0010 -> BUG-0010 — введена storage policy: DELETE для синхронизируемых/сетевых/съёмных путей, WAL для безопасного локального диска; поддержаны SAYURI_DATA_DIR и SAYURI_SQLITE_JOURNAL_MODE.
- CHG-0055 / BUG-0011 — JobManager бесконечно удерживал завершённые jobs и futures.
- CHG-0056 / FIX-0011 -> BUG-0011 — futures освобождаются после завершения, история jobs ограничена job_history_limit.
- CHG-0057 / BUG-0012 — /api/health запускал SQLite quick_check при каждом polling.
- CHG-0058 / FIX-0012 -> BUG-0012 — обычный status лёгкий; quick_check выполняется только в deep-status и диагностике.
- CHG-0059 / BUG-0013 — updater всегда использовал origin/main.
- CHG-0060 / FIX-0013 -> BUG-0013 — updater определяет configured upstream текущей ветки и обновляет только его.
- CHG-0061 / BUG-0014 — BAT и tray показывали устаревшую версию v0.1.0.
- CHG-0062 / FIX-0014 -> BUG-0014 — пользовательские подписи версии читаются из VERSION.
- CHG-0063 / BUG-0015 — версии проекта и ядер дублировались по Python-файлам.
- CHG-0064 / FIX-0015 -> BUG-0015 — введён единый src/sayuri_yukishiro/version.py; системное ядро обновлено до v0.2.1.
- CHG-0065 / BUG-0016 — launcher.ps1 присваивал автоматической переменной PowerShell $args.
- CHG-0066 / FIX-0016 -> BUG-0016 — локальные массивы аргументов переименованы в cliArgs/processArgs.

Проверки:

- tests: PASS
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PASS
- protocol-validation: PASS
- python-compile: PASS
- powershell-syntax: PASS

Commit:

72afefdb47abd263ed4615f8ae63c4da37ee829a

Следующий шаг:

next_action: v0.4.0 — Система модулей и их жизненный цикл: manifests, discovery, dependency graph, permissions, migrations, health-check, controlled startup/shutdown и регистрация способностей модулей в когнитивном ядре.


---

## v0.4.0

Дата: 2026-10-07

Статус: in_progress

Изменения:

- CHG-0067 / ARCH-0007 — обновление проекта переносится в системное ядро как привилегированная инфраструктурная служба, а не модуль.
- CHG-0068 / FEAT-0026 — добавляется управляемая служба UpdateService: состояние, проверка upstream, доступная версия, список изменений и журнал операции.
- CHG-0069 / FEAT-0027 — добавляется долговечное состояние обновлений, staging/backup metadata и журнал обновления вне изменяемых файлов проекта.
- CHG-0070 / FEAT-0028 — добавляется API ядра GET /api/update/status, POST /api/update/check и POST /api/update/apply с локальной защитой управляющим токеном.
- CHG-0071 / FEAT-0029 — добавляется отдельный update-helper: ожидание мягкой остановки, backup, fast-forward apply, post-update verification, rollback и restart.
- CHG-0072 / FEAT-0030 — в системную web-оболочку добавляется встроенная страница «Обновления проекта» с проверкой, применением, прогрессом и журналом.
- CHG-0073 / FEAT-0031 — в Windows tray добавляется пункт «Обновления проекта», использующий тот же API и открывающий встроенную страницу.
- CHG-0074 / IMP-0004 — старое автоматическое изменение репозитория из preflight отключается; обновления имеют единый owner — UpdateService.
- CHG-0075 / BUG-0017 — явный git fetch ветки мог обновить только FETCH_HEAD, оставив tracking-ref upstream устаревшим.
- CHG-0076 / FIX-0017 -> BUG-0017 — fetch выполняется с явным refspec в refs/remotes/<remote>/<branch>, после чего UpdateService сравнивает свежий upstream SHA.
- CHG-0077 / BUG-0018 — машинный реестр ID получил лишние символы после JSON-объекта и перестал разбираться валидатором.
- CHG-0078 / FIX-0018 -> BUG-0018 — UPDATE_IDS.json переписан валидным JSON с корректным завершением файла.
- CHG-0079 / BUG-0019 — новые строки журнала CHG-0075…0078 были записаны как буквальные backslash+n и не распознавались как отдельные записи.
- CHG-0080 / FIX-0019 -> BUG-0019 — секция v0.4.0 журнала переписана реальными переводами строк, чтобы каждый ID был отдельной записью.
- CHG-0081 / BUG-0020 — Windows CI preflight упал с UnicodeEncodeError при выводе русского названия «Обновления проекта» через cp1252 stdout.
- CHG-0082 / FIX-0020 -> BUG-0020 — CLI принудительно конфигурирует stdout/stderr как UTF-8 до первого пользовательского вывода.
- CHG-0083 / BUG-0021 — параллельная фиксация BUG-0020 дважды добавила CHG-0081/CHG-0082 и BUG-0020/FIX-0020 в журнал и reserved ID.
- CHG-0084 / FIX-0021 -> BUG-0021 — дубли удалены из reserved; журнал должен был содержать только одну каноническую пару BUG-0020/FIX-0020.
- CHG-0085 / BUG-0022 — FIX-0021 оказался неполным: дубли BUG-0020/FIX-0020 остались в UPDATE_LOG.md.
- CHG-0086 / FIX-0022 -> BUG-0022 — секция v0.4.0 нормализована и содержит ровно по одной первичной записи каждого ID.
- CHG-0087 / BUG-0023 — после helper-restart без постоянного tray-token web-страница могла сохранить старый control-token и получить 403.
- CHG-0088 / FIX-0023 -> BUG-0023 — web-оболочка сбрасывает cached control-token после reconnect и повторно получает token при 403.
- CHG-0089 / BUG-0024 — rollback helper мог выполнить git reset --hard даже если после apply появились новые локальные изменения.
- CHG-0090 / FIX-0024 -> BUG-0024 — перед rollback helper повторно требует чистый worktree; при локальных изменениях reset запрещён, backup сохраняется.
- CHG-0091 / BUG-0025 — если новое ядро запускалось, но не становилось healthy, helper мог начать rollback пока неудачный процесс ещё держал файлы и БД.
- CHG-0092 / FIX-0025 -> BUG-0025 — restart гарантированно завершает неуспешный новый процесс до перехода к rollback.
- CHG-0093 / BUG-0026 — control-token совпадал с shutdown-token, а HTTP Host не проверялся, что излишне связывало привилегии и оставляло поверхность для DNS rebinding.
- CHG-0094 / FIX-0026 -> BUG-0026 — control-token становится отдельным секретом; privileged local API требует loopback client и loopback Host.
- CHG-0095 / BUG-0027 — после аварийного завершения update-helper persisted phase мог навсегда остаться busy и блокировать новые проверки.
- CHG-0096 / FIX-0027 -> BUG-0027 — UpdateService при старте отличает живой helper от stale operation и переводит прерванное обновление в recoverable failed state.
- CHG-0097 / BUG-0028 — tray после update-restart мог привязаться к любому процессу на порту, если тот имитировал /api/health.
- CHG-0098 / FIX-0028 -> BUG-0028 — tray повторно захватывает PID только когда /api/health подтверждает project = Sayuri Yukishiro.
- CHG-0099 / BUG-0029 — параллельная регистрация transactional hardening повторно использовала CHG-0089/0090 и BUG-0024/FIX-0024 для другого дефекта, рассинхронизировав журнал и счётчики.
- CHG-0100 / FIX-0029 -> BUG-0029 — ID нормализованы: CHG-0089/0090 остаются за безопасностью rollback, CHG-0091…0098 сохраняются, конфликтующий дефект получает новую уникальную пару.
- CHG-0101 / BUG-0030 — post-update verification использовал production data и мог применить миграции БД до окончательного успеха; rollback кода не гарантировал откат данных.
- CHG-0102 / FIX-0030 -> BUG-0030 — verification получает изолированный SAYURI_DATA_DIR; перед apply создаются SQLite backup-снимки production БД, которые восстанавливаются при rollback.

Проверки:

- tests: PENDING
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PENDING
- protocol-validation: PENDING
- python-compile: PENDING
- powershell-syntax: PENDING

Commit:

PENDING_AFTER_IMPLEMENTATION_CHECKS

Следующий шаг:

next_action: реализовать оставшееся transactional hardening BUG-0025…BUG-0030, выполнить полный CI и финализировать v0.4.0.
