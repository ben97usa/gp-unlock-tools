@echo off
setlocal

set PXE_USER=qsitoan
set PXE_IP=192.168.202.50
set REMOTE_SCRIPT=/home/qsitoan/UNLOCK_GP/collect_csr_only_to_pxe.py
set REMOTE_BASE=/home/RMA_GPCARD/CSR
set LOCAL_BASE=C:\Users\QSI-LOANER-4233\Desktop\RMA_GPCARD

set /p PXE_PASS=Enter PXE password: 

echo ==========================================
echo Running CSR collect script on PXE...
echo ==========================================

ssh %PXE_USER%@%PXE_IP% "python3 %REMOTE_SCRIPT% \"%PXE_PASS%\"" > pxe_csr_output.txt

if errorlevel 1 (
    echo Remote script failed.
    type pxe_csr_output.txt
    pause
    exit /b 1
)

set FINAL_FOLDER=
for /f "tokens=2 delims==" %%A in ('findstr /B "FINAL_CSR_FOLDER_NAME=" pxe_csr_output.txt') do (
    set FINAL_FOLDER=%%A
)

if "%FINAL_FOLDER%"=="" (
    echo Could not find FINAL_CSR_FOLDER_NAME from PXE output.
    type pxe_csr_output.txt
    pause
    exit /b 1
)

echo ==========================================
echo PXE CSR folder: %FINAL_FOLDER%
echo ==========================================

set LOCAL_FOLDER=%LOCAL_BASE%\%FINAL_FOLDER%

if not exist "%LOCAL_FOLDER%" (
    echo Creating local folder: %LOCAL_FOLDER%
    mkdir "%LOCAL_FOLDER%"
) else (
    echo Local folder already exists: %LOCAL_FOLDER%
)

echo ==========================================
echo Downloading CSR files from PXE to local...
echo ==========================================

scp -r %PXE_USER%@%PXE_IP%:%REMOTE_BASE%/%FINAL_FOLDER%/* "%LOCAL_FOLDER%"

if errorlevel 1 (
    echo SCP download failed.
    pause
    exit /b 1
)

echo ==========================================
echo DONE
echo Local folder: %LOCAL_FOLDER%
echo ==========================================

pause