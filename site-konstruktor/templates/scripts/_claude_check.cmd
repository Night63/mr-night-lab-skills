@echo off
rem Проверка функции БЕЗ вывода секретов: версия, режим оплаты, какие переменные заданы (только имена),
rem таймеры, прямой вызов. НИКОГДА не использовать здесь «yc config list» — он печатает токен.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set YC=%USERPROFILE%\yandex-cloud\bin\yc.exe
set FUNC={{FUNCTION_NAME}}
set LOG=%~dp0_claude_check.log
echo === START %date% %time% > "%LOG%"
echo --- версия >> "%LOG%"
"%YC%" serverless function version get-by-tag --function-name %FUNC% --tag $latest --format json --jq "{id: .id, created: .created_at, runtime: .runtime, timeout: .execution_timeout}" >> "%LOG%" 2>&1
echo --- режим оплаты >> "%LOG%"
"%YC%" serverless function version get-by-tag --function-name %FUNC% --tag $latest --format json --jq "{RK_TEST: .environment.RK_TEST, RK_RECEIPT: .environment.RK_RECEIPT}" >> "%LOG%" 2>&1
echo --- имена переменных (без значений) >> "%LOG%"
"%YC%" serverless function version get-by-tag --function-name %FUNC% --tag $latest --format json --jq ".environment | keys" >> "%LOG%" 2>&1
echo --- таймеры >> "%LOG%"
"%YC%" serverless trigger list >> "%LOG%" 2>&1
echo --- прямой вызов (корень) >> "%LOG%"
"%YC%" serverless function invoke --name %FUNC% -d "{\"httpMethod\":\"GET\",\"path\":\"/\"}" >> "%LOG%" 2>&1
echo === DONE >> "%LOG%"
