# PowerShell script to create a scheduled task for the trading bot

# --- Configuration ---
$TaskName = "RubiconTradingBot"
$TaskDescription = "Starts the Rubicon trading bot automatically on system startup."
# Get the full path to the project root directory where the script is run
$ProjectDirectory = (Resolve-Path -Path ".").Path
$ScriptPath = Join-Path $ProjectDirectory "scripts\start_bot.bat"

# --- Define Task Action ---
# The action is to run our batch script
$TaskAction = New-ScheduledTaskAction -Execute $ScriptPath

# --- Define Task Trigger ---
# This trigger runs the task when the computer starts up
$TaskTrigger = New-ScheduledTaskTrigger -AtStartup

# --- Define Task Principal ---
# This runs the task with the SYSTEM account, so it runs even if no user is logged in.
# It also runs with the highest privileges.
$TaskPrincipal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# --- Define Task Settings ---
# Configure restart settings and other options
$TaskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([System.TimeSpan]::Zero) # No time limit
# If the task fails, retry every 5 minutes, up to 3 times.
$TaskSettings.RestartCount = 3
$TaskSettings.RestartInterval = (New-TimeSpan -Minutes 5)
# Corrected: Use a valid value for MultipleInstances. 'IgnoreNew' will prevent new instances if one is already running.
$TaskSettings.MultipleInstances = "IgnoreNew"

# --- Register the Task ---
Write-Host "Registering scheduled task: $TaskName"
try {
    # Unregister task if it already exists to ensure a clean slate
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

    Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $TaskTrigger -Principal $TaskPrincipal -Settings $TaskSettings -Description $TaskDescription

    Write-Host "✅ Task '$TaskName' created successfully."
    Write-Host "The bot will now start automatically when the computer boots."
    Write-Host "You can manage the task in the Windows Task Scheduler."
} catch {
    Write-Error "❌ Failed to create scheduled task. Error: $_"
    Write-Host "Please try running this script as an Administrator."
}

# Keep the window open to see the output
Read-Host -Prompt "Press Enter to exit"