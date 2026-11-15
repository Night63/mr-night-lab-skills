@echo off
rem Инфраструктура резервного копирования и таймер (один раз на проект). Секретов не создаёт и не выводит:
rem статический ключ сервисного аккаунта создаёт ВЛАДЕЛЕЦ в консоли и сразу кладёт в менеджер паролей.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set YC=%USERPROFILE%\yandex-cloud\bin\yc.exe
set FUNC={{FUNCTION_NAME}}
set FUNC_SA={{FUNCTION_SA}}
set BK={{PROJECT}}-backup
set BK_SA=backup-writer
set LOG=%~dp0_claude_infra.log
echo === START %date% %time% > "%LOG%"

rem 1. Закрытый бакет копий (без публичного доступа)
"%YC%" storage bucket create --name %BK% --default-storage-class standard --max-size 1073741824 >> "%LOG%" 2>&1
rem 2. Правила хранения: daily/manual/pre-restore — 30 дней, weekly — 180. Формат файла сверить: yc storage bucket update --help
> "%~dp0lifecycle.json" echo [{"id":"daily","enabled":true,"filter":{"prefix":"daily/"},"expiration":{"days":30}},{"id":"manual","enabled":true,"filter":{"prefix":"manual/"},"expiration":{"days":30}},{"id":"pre","enabled":true,"filter":{"prefix":"pre-restore/"},"expiration":{"days":30}},{"id":"weekly","enabled":true,"filter":{"prefix":"weekly/"},"expiration":{"days":180}}]
"%YC%" storage bucket update --name %BK% --lifecycle-rules-from-file "%~dp0lifecycle.json" >> "%LOG%" 2>&1
rem 3. Сервисный аккаунт БЕЗ ролей на каталог; доступ только к этому бакету через ACL (READ + WRITE)
"%YC%" iam service-account create --name %BK_SA% >> "%LOG%" 2>&1
set "SAID="
for /f "usebackq delims=" %%A in (`"%YC%" iam service-account get --name %BK_SA% --format json --jq .id`) do set "SAID=%%A"
"%YC%" storage bucket update --name %BK% --grants grant-type=grant-type-account,grantee-id=%SAID%,permission=permission-read --grants grant-type=grant-type-account,grantee-id=%SAID%,permission=permission-write >> "%LOG%" 2>&1
rem 4. Суточный таймер (03:00 UTC): чистка ПД + копия базы
"%YC%" serverless trigger create timer --name %FUNC%-daily --cron-expression "0 3 * * ? *" --invoke-function-name %FUNC% --invoke-function-service-account-name %FUNC_SA% >> "%LOG%" 2>&1

rem 5. Проверка — по облаку, а не по коду
echo --- bucket >> "%LOG%" & "%YC%" storage bucket get --name %BK% --full >> "%LOG%" 2>&1
echo --- triggers >> "%LOG%" & "%YC%" serverless trigger list >> "%LOG%" 2>&1
del "%~dp0lifecycle.json" >nul 2>&1
echo === DONE >> "%LOG%"
