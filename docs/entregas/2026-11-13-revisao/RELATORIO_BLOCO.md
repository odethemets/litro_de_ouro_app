# Compatibilidade, revisão das entregas e SDK

Data/fuso: 13/11/2026, America/Fortaleza.
Referência: branch `main`, HEAD `0ec3c786b2f07e32c7e06d0cf73da5c9b9ee9194`, com árvore previamente modificada e arquivos não rastreados.
Responsável técnico: Codex local; revisão técnica própria. Revisão independente não realizada.

Escopo inicial: preparar a revisão de oferta/votos/avisos já integrados, conferir os controles e a discrepância do SDK. Orientação mais recente do responsável: nas próximas entregas o Codex **confere compatibilidade, aplica o código recebido, executa testes e gera relatório, diff e resultados**. Não assumir novamente planejamento/construção autônoma de novas funcionalidades. As alterações abaixo já estavam iniciadas quando essa orientação chegou e foram concluídas e verificadas.

## Resultado observável

Antes, o container não encontrava `google.genai`; `requirements.txt` declarava `google-generativeai==0.8.3`, que fornece outro SDK. Os testes de IA substituíam os módulos por simuladores e não detectavam essa ausência.

Depois, `google-genai==2.34.0` está declarado e instalado em uma imagem construída sem cache. O import real e os tipos utilizados por foto/texto passaram sem criar cliente ou chamar o Gemini. Essa imagem foi aplicada apenas ao backend Docker local. O healthcheck, login fictício/perfil e catálogo continuam funcionando.

Não foram reimplementados oferta, votos ou fila. Foi acrescentado um cenário de integração para comprovar que um novo preço não herda os votos do preço anterior.

## Identificação incremental

Antes de editar, foram copiadas somente fontes/configurações públicas pertinentes para `base/`, com hashes em `BASE_SHA256.json`. Não foram copiados `.env`, certificados privados, tokens ou dados pessoais do banco. `base/` contém o estado **no início desta rodada**, já com a entrega anterior, e inclui funções centrais completas e testes para revisão.

Não existe um snapshot confiável anterior à implementação da rodada passada. Por isso **não foi inventado um patch retrospectivo** nem usado um diff de toda a árvore contra o HEAD como se fosse incremental. Para essa entrega anterior, usa-se a alternativa autorizada na especificação: arquivos pertinentes completos em `base/`, acompanhados de [explicação técnica](OFERTAS_VOTOS_AVISOS.md). Os arquivos novos da rodada passada são identificados nessa explicação.

O arquivo `ALTERACOES_CODIGO.patch` contém apenas a diferença desta rodada de revisão: requisito, novo verificador e novo cenário. A cópia binária original do requisito é preservada, pois ele estava em UTF-16LE com BOM. Foi convertido para UTF-8 sem BOM; o patch inclui essa conversão binária. Relatórios e logs são entregues integralmente neste diretório, sem embuti-los recursivamente no próprio patch. `RESULTADO_SHA256.json` identifica os fontes finais alterados e os artefatos de revisão.

## Arquivos/símbolos desta rodada

| Arquivo | Símbolo e alteração |
| --- | --- |
| `back_end/requirements.txt` | Substitui `google-generativeai==0.8.3` por `google-genai==2.34.0`; normaliza a codificação. Demais requisitos preservados. |
| `back_end/scripts/verificar_sdk_ia.py` (novo) | `verificar`: compara versão declarada/instalada, imports usados pela rota e tipos `HttpOptions`, `ThinkingConfig`, `GenerateContentConfig`, `Part`; não cria cliente. |
| `back_end/tests/integracao_participacao.py` | `test_novo_preco_nao_herda_avaliacoes`: o catálogo aponta ao novo ID, seu score é 1 e não há votos; a avaliação anterior permanece no ID anterior. |
| `RELATORIO_CONTINUIDADE.md` | Acrescenta os resultados e o limite de função definido pelo responsável. |
| Este diretório | Especificação recebida, fontes de referência, hashes, patch, comandos, análise técnica e resultados individuais. |

Fontes de produto anteriormente alterados foram preservados. Não houve edição de migrações, Compose, regras de moderação, preços/ofertas de locais reais ou preferências da conta do responsável.

Nenhum arquivo de código alterado nesta rodada ultrapassa 500 linhas. Há fontes de contexto anteriores maiores, como `test_infra_banco.py`, `test_transferencia_tidb.py` e `ia.py`; foram apenas copiados como referência, sem refatoração cosmética para alterar contagem.

## SDK/configuração/desempenho

O projeto usa os imports `google.genai` e `google.genai.types`. Foi selecionada a versão fixa 2.34.0, compatível com Python >=3.11, para preservar a família 2 do SDK e evitar agregar mudanças de versão principal ao reparo. A imagem limpa usou Python 3.12.16. Foram conferidos os [metadados da versão](https://pypi.org/pypi/google-genai/2.34.0/json) e a [documentação oficial de imports](https://googleapis.github.io/python-genai/).

Os requisitos diretos continuam parcialmente sem pin de versão (por exemplo Pillow), e as dependências transitivas são resolvidas pelo pip. Logo, esta é evidência de **instalação limpa nesta execução**, não um lock integral reprodutível bit a bit. `PACOTES_IMAGEM.txt` registra o conjunto resolvido. `PIP_CHECK.log` não aponta dependências quebradas. Não se mediu memória, latência ou tamanho antes/depois; não há alegação de otimização comprovada.

Não houve mudança de `GEMINI_API_KEY`, modelo, quota, endpoint nem timeout das rotas. O Compose continua com a chave vazia, e o raio local continua em 50 km. Não foi feita chamada paga, envio de imagem ou requisição a modelo. O Python/venv do Windows não foi alterado nem homologado; a instalação foi verificada no runtime Docker. A nova exigência de Python >=3.11 deve ser respeitada ao criar outro venv.

## Verificações executadas

Comandos completos, destinos e separação de operações em [COMANDOS_EXECUTADOS.md](COMANDOS_EXECUTADOS.md).

| Verificação | Runtime/destino | Resultado | Evidência |
| --- | --- | --- | --- |
| Build com `--no-cache` | Docker, tag `revisao-sdk-20261113` | Aprovado; instalação pelos requisitos declarados | `BUILD_SDK.log` |
| Verificador SDK sem rede | Container descartável com `--network none` | Versão 2.34.0 e tipos reais válidos; sem cliente/chamada | `SDK_IMAGEM_LIMPA.log` |
| `pip check` / `pip freeze` | Imagem limpa sem rede | Aprovado / versões registradas | `PIP_CHECK.log`, `PACOTES_IMAGEM.txt` |
| Recriação somente backend | Docker local, `--no-deps` | Saudável; db e volumes preservados | `APLICACAO_SDK.log` |
| Verificador SDK | Backend local em execução | Aprovado; imports das rotas correspondem ao SDK | `SDK_RUNTIME.log` |
| Sete suítes offline | Backend com SDK instalado | 128 casos unittest, mais scripts de assertivas de IA/geofence, aprovados | `TESTES_BACKEND.log` |
| Integração completa | MySQL/TLS, banco descartável explícito, raio 500 m, GPS sintético | **14 cenários aprovados** | `INTEGRACAO_MYSQL.log` |
| TypeScript/lint | Node local, `front_end` | Ambos exit 0 | `TYPESCRIPT.log`, `LINT.log` |
| Testes frontend | Node, contratos/estados simulados | **82 aprovados** | `TESTES_FRONTEND.log` |
| Verificador local | Banco `litro_de_ouro_dev`, leituras/login fictício | TLS/API/perfil ok; 59 postos, 1 usuário, 11 preços, 0 votos | `SAUDE_LOCAL.log` |

Não foi reduzida cobertura nesta rodada. A limitação dos antigos simuladores às migrações 001/002 veio da rodada anterior e está explicada em `OFERTAS_VOTOS_AVISOS.md`; a integração usa as quatro migrações no servidor real.

O banco descartável foi recriado exclusivamente para os testes, depois removido e seu grant temporário revogado. Falhas injetadas aparecem como ERROR nos logs de teste de rollback e são esperadas; os cenários terminaram aprovados.

**Não executado:** homologação visual, capturas de UI, navegador estreito, aparelho físico, alcance pelo celular, GPS/microfone reais, e-mail/provedores e fluxo humano com duas contas. A ferramenta de uso do computador interrompeu a tentativa no Firefox com a mensagem: “browser URL policy enforcement is not yet supported for the current Windows browser”. Não foram feitas ações na página nem usado outro caminho para contornar a interrupção. Nenhuma captura é apresentada como evidência inexistente. Não houve nova exportação web nesta rodada porque não mudou código frontend; a exportação anterior permanece evidência histórica.

## Revisão e reversão

O patch foi produzido contra `base/`, incluindo o arquivo novo. O módulo SDK foi verificado pela própria sessão; não atribuir revisão independente. A análise detalha ordem de locks e limites de concorrência: os testes não provam ausência de todo deadlock possível entre operações distintas.

Para reverter somente os códigos desta rodada: conferir que o conteúdo atual ainda corresponde aos hashes finais; aplicar o patch em reverso com `git apply --reverse --check` antes de efetivar. Alternativamente, restaurar **somente** os dois arquivos existentes de `base/` e remover o novo verificador após conferir seu hash. O requisito original em UTF-16 está preservado nessa base. Nenhum desses procedimentos deve sobrescrever mudanças posteriores sem revisão.

Para reverter o runtime, foi preservada a imagem anterior como `litro-de-ouro-backend-local:antes-sdk-20261113`, com ID em `IMAGEM_ANTERIOR.txt`. Retag dessa imagem para `:dev` e recriação somente do backend restauram o runtime anterior; não remover volumes. A reversão do código não desfaz contribuições já confirmadas. Nesta rodada não houve novas contribuições no banco do responsável nem aplicação de migrações.

## Próximo passo

Conferir os controles no navegador/aparelho quando houver uma superfície de teste acessível; o roteiro está na análise técnica. Nas próximas entregas, receber os arquivos do responsável, conferir contratos/dependências, aplicar, testar e entregar relatório/diff/resultados. Limiares de moderação, contratação/configuração de serviços e publicação continuam separados. Nenhuma publicação ou agendamento foi realizado.
