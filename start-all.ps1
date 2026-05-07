$ErrorActionPreference = "Stop"

Write-Host "Starting Pathogen Economy Epiforecast services..." -ForegroundColor Green

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$py = if (Test-Path $venvPython) { "`"$venvPython`"" } else { "python" }
$streamlitCmd = if (Test-Path $venvPython) { "& `"$venvPython`" -m streamlit run app.py" } else { "python -m streamlit run app.py" }
$apiCmd = "& $py -m pip install -q fastapi uvicorn; & $py -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$projectRoot`"; $apiCmd"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$projectRoot`"; $streamlitCmd"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$projectRoot\mobile-app`"; npm run start:expo"

Write-Host "API, Streamlit, and Expo started in separate terminals." -ForegroundColor Cyan
Write-Host "Expo runs on port 8082 (avoids Metro default 8081 conflicts)." -ForegroundColor Yellow
Write-Host "In the Expo terminal: scan the QR code with Expo Go, or press w for web." -ForegroundColor Yellow
