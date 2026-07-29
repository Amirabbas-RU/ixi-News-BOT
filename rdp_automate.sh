#!/bin/bash
# Automate RDP copy via xdotool

WINDOW=10485762

focus_window() {
    xdotool windowactivate $WINDOW
    sleep 1
}

send_keys() {
    xdotool type --window $WINDOW "$1"
    sleep 0.5
}

press_key() {
    xdotool key --window $WINDOW "$1"
    sleep 1
}

# Reset to desktop
focus_window
press_key super+d
sleep 1

# Open Run
press_key super+r
sleep 2

# Open cmd.exe
send_keys "cmd.exe"
press_key Return
sleep 4

# Test the share is accessible
send_keys "dir \\\\tsclient\\share\\main.exe"
press_key Return
sleep 3

# Create destination dir
send_keys 'if not exist "C:\Users\Administrator\Desktop\Economic News" mkdir "C:\Users\Administrator\Desktop\Economic News"'
press_key Return
sleep 3

# Copy the file
send_keys 'copy \\tsclient\share\main.exe "C:\Users\Administrator\Desktop\Economic News" /Y'
press_key Return
sleep 10

# Verify
send_keys 'if exist "C:\Users\Administrator\Desktop\Economic News\main.exe" (echo SUCCESS > \\tsclient\share\result.txt) else (echo FAILED > \\tsclient\share\result.txt)'
press_key Return
sleep 3

echo "Automation script completed"
