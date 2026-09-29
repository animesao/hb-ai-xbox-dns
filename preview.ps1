# Рисует окно программы в preview.png без запуска (права администратора не нужны)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$exe = Join-Path $PSScriptRoot "HB_AI_Xbox_DNS.exe"
$asm = [Reflection.Assembly]::LoadFile($exe)
$f = [Activator]::CreateInstance($asm.GetType("HbAi.XboxDns.MainForm"), $true)
$f.CreateControl()
$bmp = New-Object System.Drawing.Bitmap $f.ClientSize.Width, $f.ClientSize.Height
$f.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle 0, 0, $bmp.Width, $bmp.Height))
$bmp.Save((Join-Path $PSScriptRoot "preview.png"))
