# scripts/sync_emails.ps1
# Motor de Sincronização Vanguard - Sincronia de E-mail via Outlook Local
# Uso: 
#   powershell.exe -File sync_emails.ps1 "1620154,1621053,..." "SHM-gestaodecp@cemig.com.br"
#   powershell.exe -File sync_emails.ps1 "ALL" "SHM-gestaodecp@cemig.com.br"

# Configuração de Encoding para evitar problemas com caracteres brasileiros
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$argSolic = if ($args.Count -ge 1 -and -not [string]::IsNullOrWhiteSpace($args[0])) { $args[0].Trim() } else { "ALL" }
$isAllMode = ($argSolic -eq "ALL" -or $argSolic -eq "*")

$solicitacoes = if (-not $isAllMode) {
    $argSolic -split "," | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
} else {
    @()
}

$resultado = @{}

try {
    # 1. Conectar ao Outlook
    $outlook = New-Object -ComObject Outlook.Application -ErrorAction Stop
    $namespace = $outlook.GetNamespace("MAPI")
    
    $emailCaixa = "SHM-man-urgencia@cemig.com.br"
    if ($args.Count -ge 2 -and -not [string]::IsNullOrWhiteSpace($args[1])) {
        $emailCaixa = $args[1].Trim()
    }
    $recipient = $namespace.CreateRecipient($emailCaixa)
    
    if ($recipient.Resolve()) {
        # 6 = olFolderInbox
        $inbox = $namespace.GetSharedDefaultFolder($recipient, 6)
        
        # Filtrar e-mails dos últimos 15 dias para cobrir feriados e fins de semana
        $dataLimite = (Get-Date).AddDays(-15).ToString("dd/MM/yyyy HH:mm")
        $filter = "[ReceivedTime] >= '$dataLimite'"
        $items = $inbox.Items.Restrict($filter)
        $items.Sort("[ReceivedTime]", $true)

        # Extração em massa via Inbox Harvesting (Lê a caixa apenas uma única vez)
        $encontrados = @{}
        $regexProtocolo = [regex]'\b\d{7}\b'

        foreach ($item in $items) {
            try {
                $texto = "$($item.Subject) $($item.Body)"
                $regexMatches = $regexProtocolo.Matches($texto)
                foreach ($m in $regexMatches) {
                    $id = [string]$m.Value
                    $encontrados[$id] = $true
                }
            } catch { continue }
        }

        if ($isAllMode) {
            $resultado = $encontrados
        } else {
            foreach ($solic in $solicitacoes) {
                $s = [string]$solic
                $sTrim = [string]$solic.TrimStart('0')
                $resultado[$s] = ($encontrados.ContainsKey($s) -or $encontrados.ContainsKey($sTrim))
            }
        }
    } else {
        if (-not $isAllMode) {
            foreach ($solic in $solicitacoes) { $resultado[[string]$solic] = $false }
        }
    }
} catch {
    if (-not $isAllMode) {
        foreach ($solic in $solicitacoes) { $resultado[[string]$solic] = $false }
    }
}

# Retorna o resultado em JSON para o Python ler
$resultado | ConvertTo-Json -Compress
