#!/usr/bin/env python3
"""Build TrueDuty with Nuitka as a standalone folder (no one-file self extractor).
   python build.py            ->  dist/TrueDuty/            (Windows, Linux: folder with TrueDuty[.exe])
                                  dist/TrueDuty.app          (macOS bundle)
Why standalone: one-file builds unpack themselves into a temp folder at every start. That pattern is what
packers used by malware do, so antivirus heuristics flag it. A plain folder of signed files, installed by a
normal installer, is the same layout every commercial app uses and is far less likely to be flagged.
Packaging (installer, portable zip, deb, rpm, AppImage, dmg, pkg) and code signing happen in CI, see
.github/workflows/release.yml and docs/code-signing.md."""
import os, sys, glob, shutil, platform, subprocess, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); OS = platform.system(); OUT = os.path.join(HERE, 'dist')
VERSION = os.environ.get('TD_VERSION') or '2.0.0'
NUM = '.'.join((VERSION.split('-')[0].split('.') + ['0', '0', '0', '0'])[:4])     # Windows wants a.b.c.d
def run(cmd):
    print('>', ' '.join(map(str, cmd)), flush=True); subprocess.check_call(cmd)

shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
cmd = [sys.executable, '-m', 'nuitka', '--standalone', '--assume-yes-for-downloads', '--enable-plugin=tk-inter',
       '--include-package=pynput', '--include-package=kyber_py', '--include-package-data=customtkinter', '--include-package-data=certifi',
       '--include-data-dir=' + os.path.join(HERE, 'assets') + '=assets', '--output-dir=' + OUT, '--output-filename=TrueDuty',
       '--company-name=QudsLab', '--product-name=TrueDuty', '--file-version=' + NUM, '--product-version=' + NUM,
       '--file-description=TrueDuty time tracker', '--copyright=Copyright (c) QudsLab. MIT License.', '--trademarks=TrueDuty']
for mod, flag in (('cffi', '--include-package=cffi'), ('_cffi_backend', '--include-module=_cffi_backend')):
    if importlib.util.find_spec(mod): cmd.append(flag)
if OS == 'Windows': cmd += ['--windows-console-mode=disable', '--windows-icon-from-ico=' + os.path.join(HERE, 'assets', 'icon.ico')]
if OS == 'Darwin': cmd += ['--macos-create-app-bundle', '--macos-app-name=TrueDuty', '--macos-app-version=' + VERSION, '--macos-app-icon=' + os.path.join(HERE, 'assets', 'app-icon.png'),
                           '--macos-signed-app-name=org.qudslab.trueduty', '--macos-app-protected-resource=NSAppleEventsUsageDescription:TrueDuty reads the name of the app you are using.']
run(cmd + [os.path.join(HERE, 'main.py')])

if OS == 'Darwin':
    app = next(iter(glob.glob(os.path.join(OUT, '*.app'))), '')
    if not app: sys.exit('no .app in ' + OUT)
    if os.path.basename(app) != 'TrueDuty.app': shutil.move(app, os.path.join(OUT, 'TrueDuty.app'))
    print('Built:', os.path.join(OUT, 'TrueDuty.app'))
else:
    dist = next(iter(glob.glob(os.path.join(OUT, '*.dist'))), '')
    if not dist: sys.exit('no .dist folder in ' + OUT)
    shutil.move(dist, os.path.join(OUT, 'TrueDuty'))
    exe = os.path.join(OUT, 'TrueDuty', 'TrueDuty.exe' if OS == 'Windows' else 'TrueDuty')
    if not os.path.exists(exe): sys.exit('no TrueDuty binary in the build folder')
    for f in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        p = os.path.join(HERE, '..', f)
        if os.path.exists(p): shutil.copy(p, os.path.join(OUT, 'TrueDuty', f))
    print('Built:', exe)
