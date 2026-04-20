@echo off
setlocal EnableDelayedExpansion

cd /d "C:\Users\QSI-LOANER-4233\Desktop\RMA_GPCARD\KeyManClient"

set PXE_USER=qsitoan
set PXE_IP=192.168.202.50
set PXE_BASE=/home/RMA_GPCARD/signed_token

set /p PXE_PASS=Enter PXE password for upload: 

echo ==========================================
echo Starting sign process for each GP_CARD_SN folder
echo ==========================================

for /d %%D in (P*) do (
    echo.
    echo ==========================================
    echo Processing folder: %%D
    echo ==========================================

    if exist "%%D\signed_token.bin" (
        echo signed_token.bin already exists in %%D
    ) else (
        echo Running sign.bat %%D
        call .\sign.bat %%D

        call :WAIT_FOR_TOKEN "%%D"
    )

    echo Creating PXE folder for %%D
    ssh %PXE_USER%@%PXE_IP% "mkdir -p %PXE_BASE%/%%D"

    echo Uploading signed_token.bin for %%D
    scp "%%D\signed_token.bin" %PXE_USER%@%PXE_IP%:%PXE_BASE%/%%D/

    if errorlevel 1 (
        echo [FAIL] Upload failed for %%D
    ) else (
        echo [OK] Uploaded %%D\signed_token.bin to PXE
    )
)

echo.
echo ==========================================
echo ALL DONE
echo ==========================================
pause
exit /b

:WAIT_FOR_TOKEN
set TARGET_FOLDER=%~1

:WAIT_LOOP
if exist "%TARGET_FOLDER%\signed_token.bin" (
    echo signed_token.bin found for %TARGET_FOLDER%
    exit /b 0
)

echo.
echo Waiting for signed_token.bin in folder %TARGET_FOLDER%
echo Complete browser login / approval, then press any key...
pause >nul
goto WAIT_LOOP