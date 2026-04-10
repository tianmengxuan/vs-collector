# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置
# 打包命令: pyinstaller vs_collector.spec
#
# 生成单文件exe: dist/VS振弦渗压计采集软件.exe

import os

block_cipher = None

# 需要打包进去的数据文件 (模板/静态资源/配置)
added_files = [
    ('templates',    'templates'),     # Flask HTML模板
    ('static',       'static'),        # CSS/JS资源
    ('config.py',    '.'),             # 配置文件
]

# 如果有图标文件，一并打包
if os.path.exists('icon.ico'):
    added_files.append(('icon.ico', '.'))

a = Analysis(
    ['gui_app.py'],          # 入口文件
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        # Flask相关
        'flask',
        'flask.templating',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'werkzeug.middleware.shared_data',
        # 项目模块
        'src',
        'src.protocol',
        'src.database',
        'src.tcp_server',
        'src.web_app',
        # 标准库
        'asyncio',
        'sqlite3',
        'logging.handlers',
        'queue',
        'threading',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'webbrowser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型包（减小体积）
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
        'IPython',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VS振弦渗压计采集软件',   # EXE文件名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,              # UPX压缩（需安装UPX）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # False = 不显示黑色命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
    # 单文件模式（所有依赖打包进一个exe）
    onefile=True,
)
