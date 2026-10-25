# Windows packages from app\dist\TrueDuty.   usage: windows.ps1 <version> <x64|arm64> <out dir>
# Makes: TrueDuty-Setup-<v>-windows-<arch>.exe (installer) and TrueDuty-<v>-windows-<arch>-portable.zip
param([string]$V, [string]$A, [string]$Out)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Resolve-Path "$here\..\dist\TrueDuty"
New-Item -ItemType Directory -Force $Out | Out-Null; $Out = (Resolve-Path $Out).Path
# portable: same signed files plus a marker, data goes to TrueDuty-data next to the exe
$p = Join-Path $env:RUNNER_TEMP "TrueDuty-$V-windows-$A-portable"
Copy-Item $src $p -Recurse -Force; New-Item -ItemType File -Force "$p\portable" | Out-Null
Compress-Archive -Path $p -DestinationPath "$Out\TrueDuty-$V-windows-$A-portable.zip" -Force
# installer
$iscc = Get-ChildItem "${env:ProgramFiles(x86)}\Inno Setup*\ISCC.exe", "$env:ProgramFiles\Inno Setup*\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $iscc) { choco install innosetup -y --no-progress | Out-Null; $iscc = Get-ChildItem "${env:ProgramFiles(x86)}\Inno Setup*\ISCC.exe", "$env:ProgramFiles\Inno Setup*\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 }
if (-not $iscc) { throw 'Inno Setup not found' }
& $iscc.FullName "/DAppVersion=$V" "/DArch=$A" "/DSrcDir=$src" "/DOutDir=$Out" "$here\trueduty.iss"
if ($LASTEXITCODE) { throw 'installer build failed' }
Get-ChildItem $Out
