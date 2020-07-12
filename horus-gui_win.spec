# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['horus-gui.py'],
             pathex=['.'],
             binaries=[('libhorus.dll','.'),('libgcc_s_seh-1.dll','.'),('libwinpthread-1.dll','.'),('libstdc++-6.dll','.')],
             datas=[],
             hiddenimports=['pkg_resources.py2_warn'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='horus-gui',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True,
          icon='doc\\horus_icon.ico')
