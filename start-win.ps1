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
  $vbox = (Get-NetAdapter | Where-Object { $_.InterfaceDescription -like '*VirtualBox*' -or $_.InterfaceDescription -like '*VMware*' -or $_.InterfaceDescription -like '*Hyper-V*' -or $_.Name -like '*WSL*' } | Select-Object -ExpandProperty ifIndex)
$lan = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { ($_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*') -and $vbox -notcontains $_.ifIndex -and $_.InterfaceAlias -notlike '*vEthernet*' -and $_.InterfaceAlias -notlike '*WSL*' } | Select-Object -First 1).IPAddress
if (-not $lan) { $lan = '127.0.0.1'; Write-Host 'No physical LAN adapter found — solo mode on 127.0.0.1.' }
  Write-Host "LAN IP: $lan  (Mac portal uses VITE_BRIDGE_URL=http://$lan`:8000)"
}
# Always rebuild the portal so start.py never serves a stale frontend\dist.
if (Get-Command npm -ErrorAction SilentlyContinue) {
  Write-Host "== Building portal =="
  Push-Location frontend
  npm install --silent
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }
  npm run build --silent
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Portal build failed" }
  Pop-Location
} else {
  Write-Host "WARNING: npm not found - serving existing frontend\dist (may be stale)."
}

.venv\Scripts\python bridge-node\start.py --lan $lan --title Terraria
