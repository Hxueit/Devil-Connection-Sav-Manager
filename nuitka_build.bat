@echo off
chcp 65001 >nul
REM Nuitka 单文件编译。本地双击运行即可；GitHub Actions（release.yml）也调用本脚本，保证两边参数一致。
REM 用法: nuitka_build.bat [输出文件名]   默认为 dcsm.exe，产物在 dist\ 目录

set "OUTPUT_NAME=%~1"
if "%OUTPUT_NAME%"=="" set "OUTPUT_NAME=dcsm.exe"

REM 检查 Nuitka 是否安装
python -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo [信息] 未检测到 Nuitka，正在安装...
    pip install "nuitka[onefile]"
    if errorlevel 1 (
        echo [错误] Nuitka 安装失败，请手动安装: pip install "nuitka[onefile]"
        if not defined CI pause
        exit /b 1
    )
)

echo.
echo [信息] 开始编译 dist\%OUTPUT_NAME% ...
echo.

python -m nuitka ^
    --onefile ^
    --assume-yes-for-downloads ^
    --windows-icon-from-ico=icon.ico ^
    --enable-plugin=tk-inter ^
    --output-dir=dist ^
    --output-filename=%OUTPUT_NAME% ^
    --windows-console-mode=disable ^
    --lto=yes ^
    --nofollow-import-to=pythonnet ^
    --nofollow-import-to=clr_loader ^
    --nofollow-import-to=cryptography ^
    --nofollow-import-to=bcrypt ^
    --nofollow-import-to=zstandard ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=pydoc ^
    --nofollow-import-to=doctest ^
    --nofollow-import-to=test ^
    --include-package=websockets ^
    main.py

if errorlevel 1 (
    echo.
    echo [错误] 编译失败！
    if not defined CI pause
    exit /b 1
)

echo.
echo [成功] 编译完成: dist\%OUTPUT_NAME%
echo.
if not defined CI pause
