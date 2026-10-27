@echo off
cd /d "%~dp0"
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:exe /out:tests.exe /main:HbAi.XboxDns.Tests ^
 /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Core.dll XboxDns.cs tests\Tests.cs || exit /b 1
"%~dp0tests.exe"
