# Windows packages from app\dist\TrueDuty.   usage: windows.ps1 <version> <x64|arm64> <out dir>
# Makes, for the given CPU:
#   TrueDuty-<v>-windows-<arch>.msi              Windows Installer package (main download; silent: msiexec /i <file> /qn)
#   TrueDuty-Setup-<v>-windows-<arch>.exe        classic setup wizard (Inno Setup), same files
#   TrueDuty-<v>-windows-<arch>-portable.zip     no install, data next to the app
# The program files in app\dist\TrueDuty are signed before this runs; the .msi and Setup .exe are signed after.
param([string]$V, [string]$A, [string]$Out)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = (Resolve-Path "$here\..\dist\TrueDuty").Path
New-Item -ItemType Directory -Force $Out | Out-Null; $Out = (Resolve-Path $Out).Path
$tmp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$num = ($V -split '[-+]')[0]                                  # MSI wants a.b.c numbers only

# ---------------- MSI (WiX Toolset 5) ----------------
$wixVer = '5.0.2'
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
  dotnet tool install --global wix --version $wixVer | Out-Host
  $env:PATH = "$env:USERPROFILE\.dotnet\tools;$env:PATH"
}
wix extension add --global "WixToolset.UI.wixext/$wixVer" | Out-Host

# every file of the build as its own component, keeping the folder layout
$xml = New-Object System.Text.StringBuilder
[void]$xml.AppendLine('<?xml version="1.0" encoding="utf-8"?>')
[void]$xml.AppendLine('<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"><Fragment><ComponentGroup Id="AppFiles" Directory="INSTALLFOLDER">')
Get-ChildItem $src -Recurse -File | Sort-Object FullName | ForEach-Object {
  $rel = $_.DirectoryName.Substring($src.Length).TrimStart('\')
  $sub = if ($rel) { ' Subdirectory="' + [Security.SecurityElement]::Escape($rel) + '"' } else { '' }
  [void]$xml.AppendLine('  <Component' + $sub + '><File Source="' + [Security.SecurityElement]::Escape($_.FullName) + '" /></Component>')
}
[void]$xml.AppendLine('</ComponentGroup></Fragment></Wix>')
$files = Join-Path $tmp 'trueduty-files.wxs'; [IO.File]::WriteAllText($files, $xml.ToString(), (New-Object Text.UTF8Encoding $false))

# license page wants RTF
$lic = Get-Content (Join-Path $here '..\..\LICENSE') -Raw
$lic = $lic.Replace('\', '\\').Replace('{', '\{').Replace('}', '\}') -replace "`r?`n", "\par`r`n"
$rtf = Join-Path $tmp 'trueduty-license.rtf'
[IO.File]::WriteAllText($rtf, "{\rtf1\ansi\deff0{\fonttbl{\f0\fswiss Segoe UI;}}\f0\fs18 $lic}", [Text.Encoding]::ASCII)

$msi = Join-Path $Out "TrueDuty-$V-windows-$A.msi"
wix build -arch $A -ext WixToolset.UI.wixext -d "Version=$num" -d "Icon=$here\..\assets\icon.ico" -d "License=$rtf" `
  -o $msi "$here\trueduty.wxs" $files
if ($LASTEXITCODE) { throw 'MSI build failed' }
Remove-Item (Join-Path $Out '*.wixpdb') -ErrorAction SilentlyContinue

# ---------------- Setup .exe (Inno Setup) ----------------
$iscc = Get-ChildItem "${env:ProgramFiles(x86)}\Inno Setup*\ISCC.exe", "$env:ProgramFiles\Inno Setup*\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $iscc) { choco install innosetup -y --no-progress | Out-Null; $iscc = Get-ChildItem "${env:ProgramFiles(x86)}\Inno Setup*\ISCC.exe", "$env:ProgramFiles\Inno Setup*\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 }
if ($iscc) {
  & $iscc.FullName "/DAppVersion=$V" "/DArch=$A" "/DSrcDir=$src" "/DOutDir=$Out" "$here\trueduty.iss"
  if ($LASTEXITCODE) { throw 'Setup .exe build failed' }
} else { Write-Warning 'Inno Setup not available: only the .msi installer was made' }

# ---------------- portable ----------------
$p = Join-Path $tmp "TrueDuty-$V-windows-$A-portable"
Copy-Item $src $p -Recurse -Force; New-Item -ItemType File -Force "$p\portable" | Out-Null
Compress-Archive -Path $p -DestinationPath "$Out\TrueDuty-$V-windows-$A-portable.zip" -Force

Get-ChildItem $Out
if (-not (Test-Path $msi)) { throw 'no .msi produced' }
