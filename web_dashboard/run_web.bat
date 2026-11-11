@echo off
chcp 65001 >nul
title Web-дашборд v16.0
cd /d "%~dp0"
python -m streamlit run app.py
pause