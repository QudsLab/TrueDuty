# Authenticode with a .pfx certificate (any CA: Certum, Sectigo, DigiCert ...).   usage: sign-pfx.ps1 <folder or file>
# Needs WIN_CERT_PFX_BASE64 and WIN_CERT_PASSWORD. Signs every .exe/.dll/.pyd that is not already validly signed.
param([string]$Path)
$ErrorActionPreference = 'Stop'
$pfx = Join-Path $env:RUNNER_TEMP 'cert.pfx'
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:WIN_CERT_PFX_BASE64))
$st = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe | Where-Object FullName -match '\\x64\\' | Sort-Object FullName | Select-Object -Last 1
$files = if (Test-Path $Path -PathType Container) { Get-ChildItem $Path -Recurse -Include *.exe, *.dll, *.pyd } else { Get-Item $Path }
foreach ($f in $files) {
  if ((Get-AuthenticodeSignature $f.FullName).Status -eq 'Valid') { continue }
  & $st.FullName sign /f $pfx /p $env:WIN_CERT_PASSWORD /fd sha256 /tr http://timestamp.digicert.com /td sha256 /d TrueDuty /du https://github.com/QudsLab/TrueDuty $f.FullName
  if ($LASTEXITCODE) { throw "signtool failed on $($f.Name)" }
}
Remove-Item $pfx
