# scripts/send_reset_email.ps1
# Dispara e-mail com código de recuperação via Outlook Local
param(
    [Parameter(Mandatory=$true)][string]$Destinatario,
    [Parameter(Mandatory=$true)][string]$Codigo,
    [Parameter(Mandatory=$true)][string]$Nome
)

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

try {
    $outlook = New-Object -ComObject Outlook.Application -ErrorAction Stop
    $mail = $outlook.CreateItem(0) # 0 = olMailItem
    $mail.To = $Destinatario
    $mail.Subject = "[Centro de Controle MT] Codigo de Recuperacao: $Codigo"
    
    $html = @"
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
    <div style="max-width: 500px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
        <div style="border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 20px;">
            <h2 style="color: #38bdf8; margin: 0; font-size: 20px;">Centro de Controle da Programação MT</h2>
            <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 13px;">Recuperação de Acesso / Redefinição de Senha</p>
        </div>
        <p style="color: #e2e8f0; font-size: 15px; line-height: 1.5;">Olá, <strong>$Nome</strong>,</p>
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">Você solicitou a redefinição de senha da sua conta no sistema. Utilize o código de verificação abaixo:</p>
        
        <div style="background: #0f172a; border: 2px dashed #38bdf8; border-radius: 8px; text-align: center; padding: 18px; margin: 25px 0;">
            <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #38bdf8; font-family: monospace;">$Codigo</span>
        </div>
        
        <p style="color: #94a3b8; font-size: 12px; line-height: 1.5;">
            ⏰ Este código é válido por <strong>10 minutos</strong> e permite até 3 tentativas de validação.<br>
            🔒 Se você não realizou esta solicitação, desconsidere este e-mail. Sua senha atual permanece inalterada.
        </p>
        <div style="border-top: 1px solid #334155; margin-top: 25px; padding-top: 15px; text-align: center;">
            <p style="color: #64748b; font-size: 11px; margin: 0;">CEMIG • Diretoria de Distribuição • Programação MT</p>
        </div>
    </div>
</body>
</html>
"@
    $mail.HTMLBody = $html
    $mail.Send()
    Write-Output '{"sucesso": true}'
} catch {
    $erroMsg = $_.Exception.Message
    $resultado = @{
        sucesso = $false
        erro = $erroMsg
    } | ConvertTo-Json -Compress
    Write-Output $resultado
}
