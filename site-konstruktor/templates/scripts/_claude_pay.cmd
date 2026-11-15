@echo off
rem Выкладка главной с живой оплатой (data-pay="on") С ПРЕДОХРАНИТЕЛЕМ:
rem загружает index.html, только если в функции RK_TEST=0. Иначе на сайте можно было бы «купить» товар
rem в тестовом режиме Робокассы без денег. Значение берётся через --jq, остальные переменные (секреты) не выводятся.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set YC=%USERPROFILE%\yandex-cloud\bin\yc.exe
set FUNC={{FUNCTION_NAME}}
set BUCKET={{DOMAIN}}
set LOG=%~dp0_claude_pay.log
echo === START %date% %time% > "%LOG%"
set "RKT="
for /f "usebackq delims=" %%A in (`"%YC%" serverless function version get-by-tag --function-name %FUNC% --tag $latest --format json --jq .environment.RK_TEST`) do set "RKT=%%A"
echo RK_TEST=[%RKT%] >> "%LOG%"
if not "%RKT%"=="0" (echo === STOP: в функции не боевой режим, сайт НЕ обновлён >> "%LOG%" & goto :eof)
findstr /c:"data-pay=\"on\"" site\index.html >nul || (echo === STOP: в index.html нет data-pay=on >> "%LOG%" & goto :eof)
"%YC%" storage s3 cp site\index.html s3://%BUCKET%/index.html --content-type text/html >> "%LOG%" 2>&1
if errorlevel 1 (echo === FAIL upload >> "%LOG%") else (echo === OK index.html с оплатой >> "%LOG%")
