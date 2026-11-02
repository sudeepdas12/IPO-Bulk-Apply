@echo off
REM Example: create a Windows Task Scheduler task to run run_bot.bat daily at 9:00 AM.
REM Edit paths and account user as needed before running.
SET TASKNAME=MeroshareBot
SET TASKRUNNER="%~dp0run_bot.bat"
REM -- run daily at 09:00 as the current user --
schtasks /Create /SC DAILY /TN %TASKNAME% /TR %TASKRUNNER% /ST 09:00 /F
echo Task created: %TASKNAME% -> %TASKRUNNER%
pause