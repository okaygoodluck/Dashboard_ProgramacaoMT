# Vanguard - Protótipo de Busca via Outlook COM
# Este script usa a instância do Outlook aberta no Windows

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "VANGUARD - TESTE DE BUSCA VIA OUTLOOK LOCAL" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

try {
    # 1. Conectar ao Outlook
    $outlook = New-Object -ComObject Outlook.Application
    $namespace = $outlook.GetNamespace("MAPI")
    Write-Host "[OK] Conectado ao Outlook." -ForegroundColor Green

    $emailCaixa = "SHM-man-urgencia@cemig.com.br"
    Write-Host "`nTentando acessar a caixa compartilhada diretamente: $emailCaixa" -ForegroundColor Cyan

    # 2. Tentar resolver o destinatário (Caixa Compartilhada)
    $recipient = $namespace.CreateRecipient($emailCaixa)
    if ($recipient.Resolve()) {
        Write-Host "[OK] Endereço '$emailCaixa' resolvido com sucesso." -ForegroundColor Green
        
        try {
            # 6 = olFolderInbox
            $inbox = $namespace.GetSharedDefaultFolder($recipient, 6)
            Write-Host "[OK] Acesso à Inbox da caixa compartilhada CONCEDIDO!" -ForegroundColor Green
            
            # Listar os e-mails
            Write-Host "`nÚltimos 5 e-mails da caixa compartilhada:" -ForegroundColor Cyan
            $items = $inbox.Items
            $items.Sort("[ReceivedTime]", $true)

            $count = 0
            foreach ($item in $items) {
                if ($count -ge 5) { break }
                Write-Host "  - [$($item.ReceivedTime.ToString('dd/MM HH:mm'))] $($item.Subject)"
                $count++
            }
        } catch {
            Write-Host "[ERRO] Você tem permissão para ver o endereço, mas não para abrir a Inbox via script: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "[ERRO] Não foi possível resolver o endereço '$emailCaixa'. Verifique se o nome está correto." -ForegroundColor Red
    }

    # 3. Fallback: Se falhou, vamos olhar dentro das pastas da conta principal
    Write-Host "`n--- BUSCA ALTERNATIVA (Dentro da conta principal) ---" -ForegroundColor Yellow
    $meuEmail = "kennedy.garito@cemig.com.br"
    $minhaPasta = $namespace.Folders | Where-Object { $_.Name -like "*$meuEmail*" }
    
    if ($minhaPasta) {
        Write-Host "Procurando 'urgencia' dentro de $($minhaPasta.Name)..."
        $sub = $minhaPasta.Folders | Where-Object { $_.Name -like "*urgencia*" }
        if ($sub) {
            Write-Host "[OK] Encontrada pasta: $($sub.Name)" -ForegroundColor Green
        } else {
            Write-Host "Nenhuma subpasta com 'urgencia' encontrada."
        }
    }

} catch {
    Write-Host "[ERRO CRÍTICO] $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "TESTE CONCLUÍDO (Pressione Enter para sair)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Read-Host # Pausa para o usuário ver o resultado
