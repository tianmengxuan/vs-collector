@echo off
chcp 65001 >nul
title VS振弦渗压计采集软件 - 打包工具

echo ============================================================
echo   VS振弦渗压计采集软件  打包脚本
echo   河北稳控科技 VS1XX/VS4XX 系列采发仪
echo ============================================================
echo.

:: ---- 检查Python ----
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python，请先安装Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] 检测到Python:
python --version

:: ---- 安装依赖 ----
echo.
echo [步骤1/4] 安装Python依赖包...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败，请检查网络或pip源
    pause
    exit /b 1
)
echo [OK] 依赖安装完成

:: ---- 安装PyInstaller ----
echo.
echo [步骤2/4] 安装PyInstaller...
pip install pyinstaller -q
echo [OK] PyInstaller 就绪

:: ---- 生成程序图标（可选） ----
echo.
echo [步骤3/4] 生成程序图标...
python -c "
try:
    from PIL import Image, ImageDraw, ImageFont
    # 创建256x256蓝色渐变图标
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 背景圆角矩形
    for i in range(256):
        alpha = 255
        r = int(30 + i * 0.6)
        g = int(60 + i * 0.3)
        b = 200
        draw.ellipse([4, 4, 252, 252], fill=(24, 80, 180, 240))
    # 文字
    draw.text((80, 90), 'VS', fill='white')
    draw.text((60, 140), '渗压', fill='#a8d4ff')
    # 保存为ICO
    img.save('icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
    print('[OK] 图标已生成: icon.ico')
except ImportError:
    print('[跳过] Pillow未安装，将使用默认图标')
except Exception as e:
    print(f'[跳过] 图标生成失败: {e}')
"

:: ---- PyInstaller 打包 ----
echo.
echo [步骤4/4] 开始打包EXE（约需2-5分钟）...
echo.

:: 清理上次打包的缓存
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller vs_collector.spec --clean --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败！请查看上方错误信息
    pause
    exit /b 1
)

:: ---- 打包后处理 ----
echo.
echo ============================================================
echo   打包成功！
echo ============================================================
echo.
echo EXE文件位置: dist\VS振弦渗压计采集软件.exe
echo.
echo 使用说明:
echo   1. 将 dist\VS振弦渗压计采集软件.exe 复制到任意目录
echo   2. 双击运行即可（无需安装Python）
echo   3. 首次运行会自动在同目录创建 data\ 和 logs\ 文件夹
echo   4. 默认TCP端口: 8866  Web端口: 5000
echo.

:: 可选：打开dist目录
set /p open_dir="是否打开输出目录？(Y/N): "
if /i "%open_dir%"=="Y" start dist

pause
