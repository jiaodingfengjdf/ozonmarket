@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

set PORT=8899
if not "%OZON_WEB_PORT%"=="" set PORT=%OZON_WEB_PORT%

echo ============================================
echo   Ozon 选品工作台
echo ============================================
echo.

REM 1) 用指纹脚本拉起 Chrome（UA 与版本对齐、默认有头、支持代理）
echo [1/2] 启动浏览器（指纹对齐模式）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_chrome.ps1"
if errorlevel 1 (
  echo   Chrome 启动失败，仍尝试继续启动服务
)

REM 2) 起服务
echo [2/2] 启动本地服务 http://127.0.0.1:%PORT%/
start "" http://127.0.0.1:%PORT%/
python web\server.py --port %PORT%

pause
