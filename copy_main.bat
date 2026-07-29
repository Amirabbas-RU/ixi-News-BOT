@echo off
echo Starting copy...
if not exist "C:\Users\Administrator\Desktop\Economic News" mkdir "C:\Users\Administrator\Desktop\Economic News"
copy \\tsclient\share\main.exe "C:\Users\Administrator\Desktop\Economic News" /Y
echo ERRORLEVEL=%ERRORLEVEL%
if exist "C:\Users\Administrator\Desktop\Economic News\main.exe" (
  echo SUCCESS
) else (
  echo FAILED
)
