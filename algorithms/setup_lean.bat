@echo off
REM TaoGrid Lean Environment Setup Script
REM Run this after installing .NET 6.0 SDK

echo ========================================
echo TaoGrid Lean Environment Setup
echo ========================================
echo.

REM Check .NET SDK
echo [1/4] Checking .NET SDK...
dotnet --version
if %errorlevel% neq 0 (
    echo ERROR: .NET SDK not found!
    echo Please install .NET 6.0 SDK from:
    echo https://dotnet.microsoft.com/download/dotnet/6.0
    pause
    exit /b 1
)
echo .NET SDK: OK
echo.

REM Check Python
echo [2/4] Checking Python version...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    pause
    exit /b 1
)
echo Python: OK
echo.

REM Install Python dependencies
echo [3/4] Installing Python dependencies...
pip install pythonnet==3.0.1
if %errorlevel% neq 0 (
    echo ERROR: Failed to install pythonnet
    pause
    exit /b 1
)

pip install quantconnect
if %errorlevel% neq 0 (
    echo ERROR: Failed to install quantconnect
    pause
    exit /b 1
)
echo Python dependencies: OK
echo.

REM Clone Lean repository
echo [4/4] Cloning Lean repository...
cd ..\..\
if not exist "Lean" (
    git clone https://github.com/QuantConnect/Lean.git
    if %errorlevel% neq 0 (
        echo ERROR: Failed to clone Lean repository
        pause
        exit /b 1
    )
    echo Lean repository cloned successfully
) else (
    echo Lean repository already exists, skipping clone
)
echo.

echo ========================================
echo Setup completed successfully!
echo ========================================
echo.
echo Next steps:
echo 1. Review algorithms/taogrid/algorithm.py
echo 2. Configure algorithms/lean-config.json
echo 3. Run: python algorithms/taogrid/algorithm.py
echo.
pause
