"""Build the distributable Windows folder: one .exe, its runtime, and the data beside it.

**One-folder, deliberately, not one-file.** A one-file build unpacks the whole Python
runtime into a temp directory on every launch and runs from there, which is exactly the
shape of a dropper and is flagged by antivirus heuristics constantly. One-folder ships
the runtime already unpacked, so nothing self-extracts, startup is faster, and the
`profiles/` folder stays visible for people to read and edit.

The layout produced is the one a game install has::

    SonicChroniclesModBuilder/
        ModPackMaker.exe        <- run this
        _internal/              <- Python runtime and libraries, do not touch
        profiles/               <- editable, including presets/
        assets/
        README.md  LICENSE  CREDITS.md

`profiles/` and `assets/` are copied *beside* the executable rather than bundled, because
`modpack_maker.FROZEN` points ROOT at the executable's folder for exactly that reason:
they are data a user edits, not code.

Usage:  py tools/build/make_release.py [--zip]
"""
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
DIST = os.path.join(ROOT, 'dist')
NAME = 'SonicChroniclesModBuilder'
OUT = os.path.join(DIST, NAME)

#: Imported lazily or through sys.path games, so static analysis can miss them.
HIDDEN = ['modbuild', 'features', 'gamedata', 'icons', 'bps', 'rom_build',
          'herf_write', 'tlk_write', 'twoda_write', 'gda_write', 'gff4_write',
          'are_write', 'gff4', 'herf', 'nds_rom', 'twoda', 'lz77', 'plotflags']
#: Copied next to the .exe, not into the bundle.
BESIDE = ['profiles', 'assets', 'README.md', 'LICENSE', 'CREDITS.md',
          'KNOWN_FORMATS.md', 'KNOWN_IDS.md']


def main():
    for d in (os.path.join(ROOT, 'build', '_pyi'), OUT):
        shutil.rmtree(d, ignore_errors=True)
    cmd = [sys.executable, '-m', 'PyInstaller',
           '--noconfirm', '--clean', '--windowed', '--onedir',
           '--name', 'ModPackMaker',
           '--distpath', os.path.join(DIST, '_stage'),
           '--workpath', os.path.join(ROOT, 'build', '_pyi'),
           '--specpath', os.path.join(ROOT, 'build', '_pyi'),
           '--icon', os.path.join(ROOT, 'assets', 'icon.ico'),
           '--paths', os.path.join(ROOT, 'tools', 'build'),
           '--paths', os.path.join(ROOT, 'tools', 'recon'),
           '--paths', os.path.join(ROOT, 'tools', 'gui')]
    for h in HIDDEN:
        cmd += ['--hidden-import', h]
    cmd.append(os.path.join(ROOT, 'tools', 'gui', 'modpack_maker.py'))
    print('running PyInstaller...')
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        print('PyInstaller failed'); return 1

    shutil.move(os.path.join(DIST, '_stage', 'ModPackMaker'), OUT)
    shutil.rmtree(os.path.join(DIST, '_stage'), ignore_errors=True)
    for item in BESIDE:
        src = os.path.join(ROOT, item)
        if not os.path.exists(src):
            continue
        dst = os.path.join(OUT, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('_built_*.json'))
        else:
            shutil.copy2(src, dst)
    print('\nbuilt %s' % OUT)
    exe = os.path.join(OUT, 'ModPackMaker.exe')
    print('  exe present:', os.path.exists(exe))
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(OUT) for f in fs)
    print('  folder size: %.1f MB' % (total / 1e6))

    if '--zip' in sys.argv:
        zp = os.path.join(DIST, NAME + '.zip')
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
            for dp, _, fs in os.walk(OUT):
                for f in fs:
                    full = os.path.join(dp, f)
                    z.write(full, os.path.join(NAME, os.path.relpath(full, OUT)))
        print('  zip: %s (%.1f MB)' % (zp, os.path.getsize(zp) / 1e6))
    return 0


if __name__ == '__main__':
    sys.exit(main())
