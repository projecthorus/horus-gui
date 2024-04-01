# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['horus-gui.py'],
             pathex=['.'],
             binaries=[('../horusdemodlib/build/src/libhorus.dylib','.')],
             datas=[],
             hiddenimports=[],
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
          [],
          exclude_binaries=True,
          name='horus-gui',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False , icon='doc/horus_logo.icns')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='horus-gui')
app = BUNDLE(coll,
             name='horus-gui.app',
             icon='doc/horus_logo.icns',
             bundle_identifier=None,
             info_plist={
                'NSMicrophoneUsageDescription': 'Horus-GUI needs audio access to receive telemetry.' 
             },
             )
