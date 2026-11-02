@echo off
REM Clean build artifacts and egg-info for packaging
echo Removing build, dist, and egg-info directories...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
for /d %%d in (*.egg-info) do rmdir /s /q "%%d"
echo Clean complete.
pause
