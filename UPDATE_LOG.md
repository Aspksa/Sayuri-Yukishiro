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

Статус: in_progress

Изменения:

- CHG-0013 / ARCH-0002 — протокол обновлений превращён в обязательное правило репозитория и добавлен AGENTS.md.
- CHG-0014 / FEAT-0006 — добавлены машинный реестр ID и валидатор протокола.
- CHG-0015 / IMP-0001 — протокол интегрируется с PROJECT_STATE.json, README и GitHub Actions.
- CHG-0016 / BUG-0004 — CI обнаружил переэкранированные regex в валидаторе, из-за чего ID не распознавались.
- CHG-0017 / FIX-0004 -> BUG-0004 — regex валидатора исправлены до корректных raw-паттернов Python.
- CHG-0018 / BUG-0005 — валидатор ошибочно считал обязательную ссылку FIX -> BUG повторным объявлением BUG-ID.
- CHG-0019 / FIX-0005 -> BUG-0005 — уникальность ID теперь проверяется по первичным объявлениям, а FIX-ссылки валидируются отдельно.

Проверки:

- tests: PENDING
- lint: NOT_CONFIGURED
- type-check: NOT_CONFIGURED
- smoke-test: PENDING
- protocol-validation: PENDING

Commit:

PENDING_AFTER_IMPLEMENTATION_CHECKS

Следующий шаг:

next_action: завершить CI v0.1.1, финализировать журнал и затем начать v0.2.0 Module Runtime & Lifecycle.
