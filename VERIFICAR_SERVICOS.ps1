param(
    [string]$Projeto = "C:\litro_de_ouro",
    [string]$PythonBackend = ""
)

$ErrorActionPreference = "Stop"
$anterior = Get-Location

try {
    $front = Join-Path $Projeto "front_end"
    $back = Join-Path $Projeto "back_end"

    if (
        -not (Test-Path -LiteralPath $front) -or
        -not (Test-Path -LiteralPath $back)
    ) {
        throw "Informe a raiz do projeto em -Projeto."
    }

    if (-not $PythonBackend) {
        $candidatos = @(
            (Join-Path $back "venv\Scripts\python.exe"),
            (Join-Path $back ".venv\Scripts\python.exe")
        )

        $PythonBackend = $candidatos |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1

        if (-not $PythonBackend) {
            throw "Informe o Python do backend em -PythonBackend."
        }
    }

    $PythonBackend = (Resolve-Path -LiteralPath $PythonBackend).Path

    Set-Location -LiteralPath $front

    Get-ChildItem -LiteralPath (Join-Path $front "tests") -File -Filter "*.test.cjs" |
        Sort-Object Name |
        ForEach-Object {
            Write-Host ("Executando " + $_.Name)

            & node $_.FullName

            if ($LASTEXITCODE -ne 0) {
                throw ("Falha: " + $_.Name)
            }
        }

    & npx tsc --noEmit

    if ($LASTEXITCODE -ne 0) {
        throw "Falha no TypeScript."
    }

    & npx eslint src/services/solicitacoesServicos.ts src/components/servicos src/services/cadastroPreco.ts src/screens/AdicionarPreco/useCadastroLote.ts src/screens/ConsultaPostos/detalhes.tsx src/screens/Configuracoes/index.tsx tests/servicos.test.cjs tests/servicos-sessao.test.cjs tests/apoio-servicos.cjs tests/fundacao.test.cjs tests/precos-lote.test.cjs

    if ($LASTEXITCODE -ne 0) {
        throw "Falha no lint do bloco de servicos."
    }

    Set-Location -LiteralPath $back

    & $PythonBackend -B scripts/testar_offline.py

    if ($LASTEXITCODE -ne 0) {
        throw "Falha nos testes offline do backend."
    }

    Write-Host "Verificacoes offline concluidas. Nenhuma migracao ou publicacao foi executada."
}
finally {
    Set-Location -LiteralPath $anterior.Path
}