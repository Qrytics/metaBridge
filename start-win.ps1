# MetaBridge Windows host setup + launch (PC = host with Terraria + mouse/keyboard).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path .venv)) { python -m venv .venv }
.venv\Scripts\pip install -q -r backend\requirements.txt -r agent\requirements.txt

Write-Host "== Windows notes =="
Write-Host "Allow TCP 8000 through the firewall when prompted (or: netsh advfirewall firewall add rule ...)."
Write-Host "Optional GPU capture: .venv\Scripts\pip install dxcam"
Write-Host "Steam > Terraria > run windowed. Mic path needs ffmpeg on PATH."
Write-Host ""

$lan = $args[0]
if (-not $lan) {
  $lan = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' } | Select-Object -First 1).IPAddress
  Write-Host "LAN IP: $lan  (Mac portal uses VITE_BRIDGE_URL=http://$lan`:8000)"
}
.venv\Scripts\python bridge-node\start.py --lan $lan --title Terraria
