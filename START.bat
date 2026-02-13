@echo off
setlocal EnableDelayedExpansion
title YouTube Scout v2

echo.
echo  =============================================
echo   YouTube Scout v2 - Intelligent Channel Finder
echo  =============================================
echo.

set "SD=%~dp0"
cd /d "%SD%"

:: -- Set PYTHONPATH early (before venv activation) --
set "PYTHONPATH=%SD%"

:: ---- [1/5] Python ----
echo [1/5] Python...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo  [ERREUR] Python non trouve dans le PATH.
    echo  Installez Python 3.10+ depuis python.org et cochez "Add to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo     Python %%v

:: ---- [2/5] Venv ----
echo [2/5] Environnement virtuel...
if not exist "%SD%venv\Scripts\activate.bat" (
    echo     Creation du venv...
    python -m venv "%SD%venv"
    if !errorlevel! neq 0 (
        echo  [ERREUR] Echec creation venv
        pause
        exit /b 1
    )
    echo     OK cree.
) else (
    echo     OK existant.
)

:: ---- [3/5] Activation ----
echo [3/5] Activation...
call "%SD%venv\Scripts\activate.bat"

:: ---- [4/5] Dependances ----
echo [4/5] Dependances...
python -m pip install --upgrade pip -q >nul 2>&1

if exist "%SD%requirements.txt" (
    pip install -r "%SD%requirements.txt" -q 2>nul
)

:: Verify dependencies are importable
python -c "import aiohttp; import psutil" >nul 2>&1
if !errorlevel! neq 0 (
    echo     Installation individuelle...
    pip install aiohttp -q 2>nul
    pip install psutil -q 2>nul
    python -c "import aiohttp; import psutil" >nul 2>&1
    if !errorlevel! neq 0 (
        echo  [ERREUR] Dependances non installees.
        echo  Essayez manuellement: pip install aiohttp psutil
        pause
        exit /b 1
    )
)
echo     OK: aiohttp + psutil

:: ---- [4b/5] Playwright + Firefox ----
echo [4b/5] Playwright + Firefox...
python -c "import playwright" >nul 2>&1
if !errorlevel! neq 0 (
    echo     Installation de playwright...
    pip install playwright -q
)
python -c "import playwright" >nul 2>&1
if !errorlevel! neq 0 (
    echo  [ATTENTION] Playwright non installe.
    echo  Executez manuellement: pip install playwright
    echo  Puis: python -m playwright install firefox
) else (
    python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.firefox.launch(headless=True); b.close(); p.stop(); print('ok')" >nul 2>&1
    if !errorlevel! neq 0 (
        echo     Installation de Firefox pour Playwright...
        python -m playwright install firefox
        if !errorlevel! neq 0 (
            echo  [ATTENTION] Firefox non installe pour Playwright.
            echo  Executez manuellement: python -m playwright install firefox
        ) else (
            echo     OK: playwright + firefox
        )
    ) else (
        echo     OK: playwright + firefox deja installes
    )
)

:: ---- [5/5] llama-server ----
echo [5/5] llama-server...
set "LLAMA_FOUND=0"
where llama-server.exe >nul 2>&1
if !errorlevel! equ 0 (
    set "LLAMA_FOUND=1"
    echo     Detecte dans PATH.
)
if "!LLAMA_FOUND!"=="0" (
    echo     [INFO] Non trouve dans PATH - specifiez le chemin dans l interface.
)

:: ---- Verification structure ----
if not exist "%SD%server\server.py" (
    echo  [ERREUR] Structure incomplete: server\server.py manquant
    echo  Verifiez que tous les dossiers sont presents.
    pause
    exit /b 1
)

:: ---- Launch ----
echo.
echo  =============================================
echo   Serveur: http://localhost:8080
echo   Ctrl+C pour arreter
echo  =============================================
echo.
title YouTube Scout v2 - http://localhost:8080

:: Open browser after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8080"

:: Run with PYTHONPATH set
python "%SD%main.py"

echo.
echo  Serveur arrete.
pause
