@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=C:\Users\User\AppData\Local\Programs\Python\Python313\python.exe"
set "FFMPEG=C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
set "FFPROBE=C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffprobe.exe"

"%PYTHON%" -m PyInstaller --noconfirm --clean --windowed --name "ControlApps Descargador" --collect-all yt_dlp --add-binary "%FFMPEG%;." --add-binary "%FFPROBE%;." run.py
if errorlevel 1 exit /b 1

rem Host de Native Messaging para la extension del navegador (solo libreria estandar; carpeta y no --onefile: arranca en 0,1 s en vez de 2-3 s)
"%PYTHON%" -m PyInstaller --noconfirm --onedir --console --name "ControlApps Descargador Host" --specpath build host_main.py
if errorlevel 1 exit /b 1

"C:\Users\User\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\ControlAppsDescargador.iss
