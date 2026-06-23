@echo off
setlocal

:: LCE to Java World Converter - Windows Wrapper

:: Navigate to the directory where the script is located
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_HASH_FILE=%VENV_DIR%\.venv_hash"

:: Check for python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: 'python' is not installed or not in PATH.
    exit /b 1
)

:: Calculate hash of requirements using Python
for /f "delims=" %%i in ('python -c "import hashlib; print(hashlib.md5(open('requirements.txt', 'rb').read()).hexdigest())"') do set REQ_HASH=%%i

set "BUILD_VENV=0"
if not exist "%VENV_DIR%" set BUILD_VENV=1
if not exist "%VENV_HASH_FILE%" set BUILD_VENV=1

if "%BUILD_VENV%"=="0" (
    set /p STORED_HASH=<"%VENV_HASH_FILE%"
)

if "%BUILD_VENV%"=="0" if not "%REQ_HASH%"=="%STORED_HASH%" (
    echo =^> Dependencies updated. Rebuilding environment...
    set BUILD_VENV=1
)

if "%BUILD_VENV%"=="1" (
    echo =^> Creating Python virtual environment in %VENV_DIR%...
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
    
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to create virtual environment.
        if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
        exit /b 1
    )
    
    echo =^> Activating virtual environment and installing dependencies...
    call "%VENV_DIR%\Scripts\activate.bat"
    
    python -m pip install --upgrade pip
    pip install -r requirements.txt

    echo %REQ_HASH% > "%VENV_HASH_FILE%"
) else (
    call "%VENV_DIR%\Scripts\activate.bat"
)

echo =^> Launching converter...
echo.

:: Execute the main Python script
python lce2je_main.py %*

:: Deactivate the virtual environment to leave the shell session clean
call deactivate

endlocal
