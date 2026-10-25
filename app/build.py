#!/usr/bin/env python3
"""Build a single-file native executable with Nuitka, then sign it.
   python build.py
Signing (optional, set env vars):
  Windows : TD_SIGN_PFX=path\\to\\cert.pfx  TD_SIGN_PASS=secret   (needs signtool from Windows SDK)  [TD_TIMESTAMP=http://timestamp.digicert.com]
  macOS   : TD_MAC_IDENTITY="Developer ID Application: Your Name (TEAMID)"
  Linux   : TD_GPG_KEY=<key id>   (writes a detached .asc signature)
A SHA-256 checksum file is always written next to the build."""
import os, sys, shutil, hashlib, platform, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); OS = platform.system(); OUT = os.path.join(HERE, 'dist')
VERSION = os.environ.get('TD_VERSION') or '2.0.0'
def run(cmd, **kw):
    print('>', ' '.join(map(str, cmd))); subprocess.check_call(cmd, **kw)
os.makedirs(OUT, exist_ok=True)
cmd = [sys.executable, '-m', 'nuitka', '--standalone' if OS == 'Darwin' else '--onefile', '--assume-yes-for-downloads', '--enable-plugin=tk-inter', '--include-package=pynput', '--include-package=kyber_py', '--include-package=cryptography', '--include-package=PIL', '--include-package=mss', '--include-package=customtkinter', '--include-package-data=customtkinter',
       '--include-package-data=certifi', '--include-data-dir=' + os.path.join(HERE, 'assets') + '=assets', '--output-dir=' + OUT, '--output-filename=TrueDuty',
       '--product-name=TrueDuty', '--company-name=QudsLab', '--file-version=' + VERSION, '--product-version=' + VERSION, '--file-description=TrueDuty time tracker']
import importlib.util
for mod, flag in (('cffi', '--include-package=cffi'), ('_cffi_backend', '--include-module=_cffi_backend')):
    if importlib.util.find_spec(mod): cmd.append(flag)
if OS == 'Windows': cmd += ['--windows-console-mode=disable', '--windows-icon-from-ico=' + os.path.join(HERE, 'assets', 'icon.ico')]
if OS == 'Darwin': cmd += ['--macos-create-app-bundle', '--macos-app-name=TrueDuty', '--macos-app-icon=' + os.path.join(HERE, 'assets', 'logo.png')]
run(cmd + [os.path.join(HERE, 'main.py')])
import glob
exe = next((p for p in [os.path.join(OUT, n) for n in ('TrueDuty.exe', 'TrueDuty.app', 'main.app', 'TrueDuty.bin', 'TrueDuty')] + glob.glob(os.path.join(OUT, '*.app')) if os.path.exists(p)), '')
if not os.path.exists(exe): sys.exit('build output not found in ' + OUT)
if OS == 'Windows' and os.environ.get('TD_SIGN_PFX'):
    run(['signtool', 'sign', '/f', os.environ['TD_SIGN_PFX'], '/p', os.environ.get('TD_SIGN_PASS', ''), '/fd', 'sha256', '/tr', os.environ.get('TD_TIMESTAMP', 'http://timestamp.digicert.com'), '/td', 'sha256', exe])
elif OS == 'Darwin' and os.environ.get('TD_MAC_IDENTITY'):
    run(['codesign', '--deep', '--force', '--options', 'runtime', '--timestamp', '--sign', os.environ['TD_MAC_IDENTITY'], exe])
elif OS == 'Linux' and os.environ.get('TD_GPG_KEY'):
    run(['gpg', '--batch', '--yes', '--armor', '--detach-sign', '-u', os.environ['TD_GPG_KEY'], exe])
else: print('NOTE: not signed (no signing env vars set). Unsigned apps trigger SmartScreen/Gatekeeper warnings.')
if os.path.isfile(exe):
    h = hashlib.sha256(open(exe, 'rb').read()).hexdigest(); open(exe + '.sha256', 'w').write(f'{h}  {os.path.basename(exe)}\n'); print('sha256', h)
print('Built:', exe)
