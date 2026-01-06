@echo off
chcp 65001 >nul
echo Nuitka 编译 单文件

REM 检查 Nuitka 是否安装
python -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Nuitka，正在安装...
    pip install nuitka
    if errorlevel 1 (
        echo [错误] Nuitka 安装失败，请手动安装: pip install nuitka
        pause
        exit /b 1
    )
)

REM 检查图标文件是否存在
if not exist "icon.ico" (
    echo [警告] 未找到 icon.ico 文件，将不使用图标
    set ICON_OPTION=
) else (
    echo [信息] 找到图标文件: icon.ico
    set ICON_OPTION=--windows-icon-from-ico=icon.ico
)

echo.
echo [信息] 开始编译...
echo.

REM 编译
python -m nuitka ^
    --onefile ^
    %ICON_OPTION% ^
    --enable-plugin=tk-inter ^
    --output-dir=dist ^
    --output-filename=dcsm.exe ^
    --windows-console-mode=disable ^
    --lto=yes ^
    --nofollow-import-to=src.modules.save_analysis.sf.debug ^
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
    pause
    exit /b 1
)

echo.
echo ========================================
echo [成功] 编译完成！
echo ========================================
echo.
pause

