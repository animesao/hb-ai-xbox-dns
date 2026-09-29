@echo off
cd /d "%~dp0"
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /optimize+ /out:"HB_AI_Xbox_DNS.exe" ^
 /win32icon:res\app.ico /win32manifest:app.manifest ^
 /resource:res\app.ico,app.ico /resource:res\Unbounded-ExtraBold.ttf,Unbounded-ExtraBold.ttf ^
 /resource:res\Manrope-Bold.ttf,Manrope-Bold.ttf /resource:res\Manrope-Medium.ttf,Manrope-Medium.ttf ^
 /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Core.dll XboxDns.cs
