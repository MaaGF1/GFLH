@echo off
title GF1靶机工具依赖安装

setlocal enabledelayedexpansion

echo ====================================
echo    GF1靶机工具依赖安装
echo ====================================
echo.

:: 尝试使用 py 启动器，优先
set PY_CMD=py -3
%PY_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    set PY_CMD=python
    %PY_CMD% --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo [错误] 未检测到 Python 环境，请先安装 Python 3.6 或更高版本。
        echo 可以从 https://www.python.org/downloads/ 下载安装。
        pause
        exit /b 1
    )
)

:: 显示 Python 版本
echo [信息] Python 环境：
%PY_CMD% --version
echo.

:: 检查 pip
%PY_CMD% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 pip，请确保 Python 安装时勾选了 "Add Python to PATH" 并正确安装 pip。
    pause
    exit /b 1
)

:: 安装 requests
echo [信息] 检查并安装所需库 (requests)...
%PY_CMD% -c "import requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 正在安装 requests...
    %PY_CMD% -m pip install --user requests
    if !errorlevel! neq 0 (
        echo [错误] 安装 requests 失败，请手动执行：pip install requests
        pause
        exit /b 1
    )
    echo [信息] requests 安装成功。
) else (
    echo [信息] requests 已安装。
)

:: 安装 frida
echo [信息] 检查并安装所需库 (frida)...
%PY_CMD% -c "import frida" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 正在安装 frida（可能需要几分钟，请耐心等待）...
    %PY_CMD% -m pip install --user frida
    if !errorlevel! neq 0 (
        echo [错误] 安装 frida 失败。这可能是因为缺少 Visual C++ 构建工具。
        echo 请尝试以下解决方案之一：
        echo 1. 安装 Visual C++ 生成工具：https://visualstudio.microsoft.com/visual-cpp-build-tools/
        echo 2. 从 https://pypi.org/project/frida/#files 下载对应 Python 版本的 wheel 文件，手动安装。
        echo 3. 以管理员身份运行此批处理再试一次。
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
    :: 安装后再次验证
    %PY_CMD% -c "import frida" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [错误] frida 安装后仍然无法导入，请手动排查。
        pause
        exit /b 1
    )
    echo [信息] frida 安装成功。
) else (
    echo [信息] frida 已安装。
)

echo.
echo [信息] 所有依赖库安装完成。
echo [信息] 可以手动运行靶机抓取工具与监视器工具。
pause
endlocal