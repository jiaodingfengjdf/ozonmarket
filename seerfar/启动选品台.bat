@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Seerfar Ozon 选品台

python -c "import openpyxl" >nul 2>&1
if errorlevel 1 (
  echo 首次运行，正在安装依赖 openpyxl ...
  pip install -r requirements.txt
)

echo.
echo   Seerfar Ozon 选品台
echo   本机访问:   http://127.0.0.1:8900/
echo   局域网地址: 见下方启动输出（形如 http://192.168.x.x:8900/）
echo   数据源: api.seerfar.cn  ^|  按 Ctrl+C 停止
echo.
start "" http://127.0.0.1:8900/
python server.py --port 8900
pause
