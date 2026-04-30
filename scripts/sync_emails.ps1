# scripts/sync_emails.ps1
# Motor de Sincronização Vanguard - Sincronia de E-mail via Outlook Local
# Uso: powershell.exe -File sync_emails.ps1 "1620154,1621053,..."

# Configuração de Encoding para evitar problemas com caracteres brasileiros
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$solicitacoes = $args[0] -split "," | ForEach-Object { $_.Trim() }
$resultado = @{}

if ($null -eq $solicitacoes -or $solicitacoes.Count -eq 0) {
    Write-Output "{}"
    exit
}

try {
    # 1. Conectar ao Outlook
    $outlook = New-Object -ComObject Outlook.Application -ErrorAction Stop
    $namespace = $outlook.GetNamespace("MAPI")
    
    $emailCaixa = "SHM-man-urgencia@cemig.com.br"
    $recipient = $namespace.CreateRecipient($emailCaixa)
    
    if ($recipient.Resolve()) {
        # 6 = olFolderInbox
        $inbox = $namespace.GetSharedDefaultFolder($recipient, 6)
        
        # Filtrar apenas e-mails dos últimos 7 dias para performance
        $dataLimite = (Get-Date).AddDays(-7).ToString("dd/MM/yyyy HH:mm")
        $filter = "[ReceivedTime] >= '$dataLimite'"
        $items = $inbox.Items.Restrict($filter)
        $items.Sort("[ReceivedTime]", $true)

        # Para cada solicitação, verificar se existe e-mail
        foreach ($solic in $solicitacoes) {
            if ([string]::IsNullOrWhiteSpace($solic)) { continue }
            
            $encontrado = $false
            # Busca otimizada: Procura o número no Assunto ou no Corpo
            # Nota: O filter do Outlook ([Subject] like ...) pode ser limitado,
            # vasculhamos a coleção filtrada por data.
            foreach ($item in $items) {
                try {
                    if ($item.Subject -like "*$solic*" -or $item.Body -like "*$solic*") {
                        $encontrado = $true
                        break
                    }
                } catch { continue }
            }
            $resultado[$solic] = $encontrado
        }
    } else {
        # Se não resolveu a caixa, marcamos tudo como falso
        foreach ($solic in $solicitacoes) { $resultado[$solic] = $false }
    }
} catch {
    # Em caso de erro (ex: Outlook fechado), retornamos tudo falso
    foreach ($solic in $solicitacoes) { $resultado[$solic] = $false }
}

# Retorna o resultado em JSON para o Python ler
$resultado | ConvertTo-Json -Compress
