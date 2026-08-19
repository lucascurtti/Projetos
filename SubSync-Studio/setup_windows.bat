@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo =====================================
echo   SubSync Studio 0.5.0 - Configuracao
echo =====================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado.
  echo Instale Python 3.12 e habilite o PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  python -m venv .venv
  if errorlevel 1 goto :erro
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :erro

python -m pip install -r requirements.txt
if errorlevel 1 goto :erro

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo [AVISO] FFmpeg nao foi encontrado no PATH.
  echo A sincronizacao so funcionara depois de instalar/configurar o FFmpeg.
) else (
  echo.
  echo [OK] FFmpeg detectado.
)

echo.
echo [OK] Instalacao concluida.
echo Abra o app por "SubSync Studio.vbs".
pause
exit /b 0

:erro
echo.
echo [ERRO] A configuracao nao foi concluida.
pause
exit /b 1
