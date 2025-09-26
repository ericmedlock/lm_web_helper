# cycle_test.ps1  — safe diagnostic; window stays open

$proj = "C:\Users\ericm\PycharmProjects\lm_web_helper"
$desk = "$env:USERPROFILE\Desktop\lm_web_helper_last.json"
$log  = Join-Path $proj "server.log"

# Show if your Tavily key is actually present in THIS session (masked length only)
Write-Host ("TAVILY_API_KEY length: " + ($env:TAVILY_API_KEY | ForEach-Object { $_.Length }) )

# 1) Cycle both tasks cleanly
schtasks /End /TN "LM Studio Server" 2>$null
schtasks /End /TN "LM Web Helper" 2>$null

schtasks /Run /TN "LM Studio Server" | Out-Null
Start-Sleep 5
schtasks /Run /TN "LM Web Helper" | Out-Null
Start-Sleep 3

# 2) Verify our API is listening
Write-Host "`nListening on 5055?"
Get-NetTCPConnection -LocalPort 5055 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess

# 3) Probe /ask and save result to Desktop
$body = @{ question = "Smoke test: reply with the single word READY." } | ConvertTo-Json
try {
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:5055/ask" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 30
  $r | ConvertTo-Json -Depth 6 | Tee-Object -FilePath $desk
} catch {
  $_ | Tee-Object -FilePath $desk
}

# 4) Task status + server log tail
Write-Host "`n--- Task: LM Web Helper (verbose) ---"
schtasks /Query /TN "LM Web Helper" /V /FO LIST

Write-Host "`n--- server.log (tail) ---"
if (Test-Path $log) { Get-Content $log -Tail 80 } else { Write-Host "no server.log yet" }

Write-Host "`nWrote result to: $desk"
Read-Host "`nDone. Press Enter to close this window"
