@echo OFF
echo Starting the Rubicon Trading Bot...

REM Change to the directory where this script is located
cd /d "%~dp0"

REM Navigate to the project root from the scripts directory
cd ..

echo Current directory: %cd%

REM Create a logs directory if it doesn't exist
IF NOT EXIST logs (
    mkdir logs
)

REM Define a log file with a timestamp
FOR /f "tokens=2 delims==" %%I in ('wmic os get LocalDateTime /value') do set "dt=%%I"
set "YYYY=%dt:~0,4%"
set "MM=%dt:~4,2%"
set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%"
set "Min=%dt:~10,2%"
set "Sec=%dt:~12,2%"
set "LogFile=logs\bot_startup_%YYYY%-%MM%-%DD%_%HH%-%Min%-%Sec%.log"

echo Logging output to %LogFile%

REM --- IMPORTANT ---
REM If you use a Python virtual environment, uncomment the following lines
REM and replace "venv" with the actual name of your environment folder (e.g., .venv).
REM
REM echo Activating virtual environment...
REM call venv\Scripts\activate

echo Launching the bot...
REM Use "python" on Windows, which is the standard.
REM The -u flag ensures that output is unbuffered and appears in logs immediately.
REM Redirect stdout and stderr to the log file.
python -u -m discord_bot.main >> %LogFile% 2>&1