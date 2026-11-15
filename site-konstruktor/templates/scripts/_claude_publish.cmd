@echo off
rem Выкладка сайта в бакет Object Storage через yc. Запуск: двойной щелчок в Проводнике (Claude кладёт скрипт
rem в подключённую папку и читает журнал _claude_publish.log). Секретов не выводит.
rem Перед первым запуском: yc установлен и выполнен yc init. Если вход истёк — откроется браузер, подтверди вход.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set YC=%USERPROFILE%\yandex-cloud\bin\yc.exe
set BUCKET={{DOMAIN}}
set SITE=%~dp0site
set LOG=%~dp0_claude_publish.log
echo === START %date% %time% > "%LOG%"

rem Типы файлов задаются ЯВНО: иначе браузер может скачать html вместо показа или не применить css.
call :put index.html text/html
call :put offer.html text/html
call :put privacy.html text/html
call :put consent.html text/html
call :put thanks.html text/html
call :put fail.html text/html
call :put robots.txt text/plain
call :put sitemap.xml text/xml
call :put assets\site.css text/css
call :put assets\site.js application/javascript
call :put assets\buy.js application/javascript
call :put assets\pay.js application/javascript
rem Программа (если есть): application/octet-stream для exe, application/zip для zip
rem call :put download\{{FILE}}.exe application/octet-stream

echo === DONE >> "%LOG%"
"%YC%" storage s3api head-object --bucket %BUCKET% --key index.html >> "%LOG%" 2>&1
goto :eof

:put
set "F=%~1"
set "K=%F:\=/%"
"%YC%" storage s3 cp "%SITE%\%F%" "s3://%BUCKET%/%K%" --content-type "%~2" >> "%LOG%" 2>&1
if errorlevel 1 (echo === FAIL %F% >> "%LOG%") else (echo === OK %F% >> "%LOG%")
goto :eof
