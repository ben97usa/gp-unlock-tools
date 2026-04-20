/*
* lần đầu trong cửa sổ PowerShell đó → hỏi password 1 lần
* chạy lại script lần 2, lần 3 trong cùng cửa sổ PowerShell → không hỏi lại
* khi đóng PowerShell → mất biến → lần sau mở lại hỏi lại 1 lần
*/

Import-Module Posh-SSH

$base = "C:\Users\QSI-LOANER-4233\Desktop\RMA_GPCARD\KeyManClient"
$hostName = "192.168.202.50"
$userName = "qsitoan"
$remoteBase = "/home/RMA_GPCARD/signed_token"

# Nhap password 1 lan
$securePassword = Read-Host "Enter PXE password" -AsSecureString
$credential = New-Object System.Management.Automation.PSCredential ($userName, $securePassword)

# Tao SSH session 1 lan
$session = New-SSHSession -ComputerName $hostName -Credential $credential -AcceptKey

if (-not $session) {
    Write-Host "Cannot create SSH session."
    exit
}

$sessionId = $session.SessionId

Get-ChildItem $base -Directory | ForEach-Object {
    $sn = $_.Name
    $token = Join-Path $_.FullName "signed_token.bin"

    if (Test-Path $token) {
        Write-Host "Uploading $sn ..."

        # Tao folder tren PXE
        Invoke-SSHCommand -SessionId $sessionId -Command "mkdir -p $remoteBase/$sn" | Out-Null

        # Upload file
        Set-SCPFile -SessionId $sessionId -LocalFile $token -RemotePath "$remoteBase/$sn/"
    }
    else {
        Write-Host "Skip $sn : no signed_token.bin"
    }
}

# Dong session khi xong
Remove-SSHSession -SessionId $sessionId

Write-Host "Done."