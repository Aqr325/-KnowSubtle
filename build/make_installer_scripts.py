#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成免工具安装器（无需 NSIS）：
  - Release-Package/Install/install.bat   (双击启动)
  - Release-Package/Install/install.ps1   (复制文件+装vc_redist+快捷方式+注册表)
  - Release-Package/Install/uninstall.ps1 (卸载)

用 utf-8-sig 写出，保证 PowerShell 正确读取中文。
"""
import pathlib

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "Release-Package" / "Install"
OUT_DIR.mkdir(parents=True, exist_ok=True)

INSTALL_PS1 = r'''# KnowSubtle Learning Universe - 免工具安装器（无需 NSIS）
$ErrorActionPreference = 'Stop'

function Test-Admin {
    return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (-not (Test-Admin)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$appName    = "KnowSubtle Learning Universe"
$appVer     = "1.0.0"
$publisher  = "KnowSubtle"
$installDir = Join-Path $env:ProgramFiles $appName
$srcDir     = Resolve-Path (Join-Path $PSScriptRoot "..")
$icon       = Join-Path $installDir "Install\程序图标.ico"
$mainExe    = Join-Path $installDir "Core\KnowSubtle\KnowSubtle.exe"
$vc         = Join-Path $installDir "Install\vc_redist.exe"
$uninstall  = Join-Path $installDir "Install\uninstall.ps1"

Write-Host "正在安装 $appName -> $installDir"
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
Copy-Item -Path "$srcDir\*" -Destination $installDir -Recurse -Force

if (Test-Path $vc) {
    Write-Host "静默安装 Visual C++ 运行库 ..."
    Start-Process -FilePath $vc -ArgumentList "/install","/quiet","/norestart" -Wait
}

$shell   = New-Object -ComObject WScript.Shell
$appMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) "Programs\$appName"
New-Item -ItemType Directory -Force -Path $appMenu | Out-Null
$lnk = Join-Path $appMenu "$appName.lnk"
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = $mainExe; $s.IconLocation = "$icon,0"; $s.WorkingDirectory = Join-Path $installDir "Core"; $s.Save()

$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) "$appName.lnk"
$d = $shell.CreateShortcut($desktop)
$d.TargetPath = $mainExe; $d.IconLocation = "$icon,0"; $d.WorkingDirectory = Join-Path $installDir "Core"; $d.Save()

$reg = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appName"
New-Item -Path $reg -Force | Out-Null
Set-ItemProperty -Path $reg -Name DisplayName     -Value $appName
Set-ItemProperty -Path $reg -Name UninstallString -Value "powershell -NoProfile -ExecutionPolicy Bypass -File `"$uninstall`""
Set-ItemProperty -Path $reg -Name DisplayVersion  -Value $appVer
Set-ItemProperty -Path $reg -Name Publisher       -Value $publisher
Set-ItemProperty -Path $reg -Name InstallLocation -Value $installDir

Write-Host "安装完成。开始菜单与桌面已生成快捷方式，可在'程序和功能'中卸载。"
'''

UNINSTALL_PS1 = r'''# KnowSubtle Learning Universe - 卸载器
$ErrorActionPreference = 'Stop'
function Test-Admin { return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
if (-not (Test-Admin)) { Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""; exit }

$appName    = "KnowSubtle Learning Universe"
$installDir = Join-Path $env:ProgramFiles $appName

$appMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) "Programs\$appName"
if (Test-Path $appMenu) { Remove-Item $appMenu -Recurse -Force }
$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) "$appName.lnk"
if (Test-Path $desktop) { Remove-Item $desktop -Force }
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
$reg = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appName"
if (Test-Path $reg) { Remove-Item $reg -Force }

Write-Host "已卸载 $appName（用户数据 %APPDATA%/KnowSubtle 已保留）。"
'''

INSTALL_BAT = r'''@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
'''

(OUT_DIR / "install.ps1").write_text(INSTALL_PS1, encoding="utf-8-sig")
(OUT_DIR / "uninstall.ps1").write_text(UNINSTALL_PS1, encoding="utf-8-sig")
(OUT_DIR / "install.bat").write_text(INSTALL_BAT, encoding="utf-8")
print("wrote:", OUT_DIR / "install.ps1")
print("wrote:", OUT_DIR / "uninstall.ps1")
print("wrote:", OUT_DIR / "install.bat")
