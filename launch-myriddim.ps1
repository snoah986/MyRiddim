$ProjectPath = "C:\Users\Admin\Downloads\ytm-player-devin"
Set-Location $ProjectPath

# Terminate lingering background processes cleanly
Get-Process python, node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Start Flask Backend silently in the background
Start-Process python -ArgumentList "backend/app.py" -WorkingDirectory $ProjectPath -WindowStyle Hidden

# Start Vite Frontend server silently in the background
Start-Process cmd -ArgumentList "/c npm run dev" -WorkingDirectory $ProjectPath -WindowStyle Hidden
Start-Sleep -Seconds 2

# Open MyRiddim interface
Start-Process "http://127.0.0.1:5193/"
