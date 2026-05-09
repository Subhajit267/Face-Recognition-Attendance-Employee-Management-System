# -*- mode: python ; coding: utf-8 -*-
import os
import face_recognition_models

# Path to face_recognition_models (contains .dat files)
models_path = os.path.dirname(face_recognition_models.__file__)

a = Analysis(
    ['main.py'],                      # your main script name
    pathex=[],
    binaries=[],
    datas=[
        ('Company_logo.jpg', '.'),    # logo image
        (models_path, 'face_recognition_models')  # face recognition model files
    ],
    hiddenimports=[
        'face_recognition_models',
        'pkg_resources',
        'cv2',
        'pymysql',                    # changed from mysql.connector
        'PIL',                        # Pillow
        'numpy',
        'face_recognition',
        'dlib'                        # required by face_recognition
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Face_Recognised_Attendance_System',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                    # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)