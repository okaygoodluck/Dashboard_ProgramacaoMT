# scripts/send_reset_email.ps1
# Dispara e-mail com codigo de recuperacao via Outlook Local
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
    <div style="max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
        <div style="border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 20px;">
            <h2 style="color: #38bdf8; margin: 0; font-size: 20px;">Centro de Controle da Programa&ccedil;&atilde;o MT</h2>
            <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 13px;">Recupera&ccedil;&atilde;o de Acesso / Redefini&ccedil;&atilde;o de Senha</p>
        </div>
        <p style="color: #e2e8f0; font-size: 15px; line-height: 1.5;">Ol&aacute;, <strong>$Nome</strong>,</p>
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">Voc&ecirc; solicitou a redefini&ccedil;&atilde;o de senha da sua conta no sistema. Utilize o c&oacute;digo de verifica&ccedil;&atilde;o abaixo na janela de recupera&ccedil;&atilde;o do sistema para cadastrar sua nova senha:</p>
        
        <div style="background: #0f172a; border: 2px dashed #38bdf8; border-radius: 8px; text-align: center; padding: 18px; margin: 25px 0;">
            <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #38bdf8; font-family: monospace;">$Codigo</span>
        </div>
        
        <div style="background: #0b1329; border-left: 4px solid #38bdf8; padding: 12px 16px; border-radius: 4px; margin-bottom: 20px;">
            <p style="color: #bae6fd; font-size: 13px; margin: 0; line-height: 1.4;">
                <strong>Aten&ccedil;&atilde;o:</strong> Este c&oacute;digo <u>n&atilde;o</u> &eacute; uma senha de acesso. Insira-o no campo <em>&ldquo;C&oacute;digo de 6 d&iacute;gitos&rdquo;</em> da janela de recupera&ccedil;&atilde;o junto com a sua nova senha definitiva.
            </p>
        </div>
        
        <p style="color: #94a3b8; font-size: 12px; line-height: 1.6; margin-bottom: 0;">
            &#9200; Este c&oacute;digo &eacute; v&aacute;lido por <strong>10 minutos</strong> e permite at&eacute; 3 tentativas de valida&ccedil;&atilde;o.<br>
            &#128274; Se voc&ecirc; n&atilde;o realizou esta solicita&ccedil;&atilde;o, desconsidere este e-mail. Sua senha atual permanece inalterada.
        </p>
        <div style="border-top: 1px solid #334155; margin-top: 25px; padding-top: 15px; text-align: center;">
            <p style="color: #64748b; font-size: 11px; margin: 0;">CEMIG &bull; Diretoria de Distribui&ccedil;&atilde;o &bull; Programa&ccedil;&atilde;o MT</p>
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
