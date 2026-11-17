# Foto do totem — aplicação local

Destinatário: Codex web. Data: 2026-11-14. Projeto: C:/litro_de_ouro.

## Resultado

Bloco aplicado e verificações automatizadas concluídas. Sete arquivos completos recebidos foram instalados sem adaptações, com igualdade SHA-256 registrada em MANIFESTO.json. Cinco arquivos locais receberam integração ou testes incrementais. Foram preservadas as alterações anteriores da árvore; nenhum commit, publicação ou migração foi executado.

A aplicação exigiu compatibilidade além dos snippets: o componente leitor não existia neste frontend, o cadastro não encaminhava foto_url e a rota tentava fazer upload após qualquer leitura bem-sucedida. Esses comportamentos locais diferem do snapshot pressuposto pela entrega.

## Integração e adaptações locais

1. AdicionarPreco: import e montagem do leitor fora de eletropostos, produtos permitidos, estado fotoUrl, associação ao valor escolhido, limpeza ao trocar posto/produto manualmente e após sucesso, encaminhamento ao envio e botão de remoção sem promessa de apagar Dropbox. A tela grande foi preservada, sem reescrita ou extração estrutural.
2. A chave do FormularioPreco agora inclui token/status além da solicitação: uma troca de sessão remonta também o formulário pai, impedindo que um comprovante associado à conta anterior sobreviva fora do leitor.
3. cadastroPreco.ts: somente campo opcional fotoUrl no pedido, foto_url no payload e encaminhamento condicional. GPS, intervalo manual, controle de envio e confirmação existentes preservados.
4. ia.py: import do helper, delegação de _preparar_imagem e _normalizar_precos e mensagem sanitizada de HTTP 400 conforme recebido. Classe _FotoInvalida, SDK/modelo/prompt, autenticação, geofence, limites e função de armazenamento existentes preservados.
5. Adaptação necessária em ia.py: upload_foto_totem só é chamado quando guardar_comprovante normalizado é true. Antes o backend ignorava o consentimento. Campo ausente/false não guarda foto. Não alterado o serviço Dropbox.
6. test_ia.py: cenários de upload e falha do Dropbox agora dão consentimento explícito; acrescentadas assertivas para campo ausente, false, 1 e sim não causarem upload. Demais verificações preservadas.
7. cadastro-preco.test.cjs: um caso adicional comprova encaminhamento opcional e remoção do comprovante sem mudar o preço.

O helper Python foi instalado antes da integração da rota, evitando import sem arquivo. Não houve alteração de dependências, Compose, geofence, navegação ou configuração de provedores. Os novos arquivos recebidos têm menos de 500 linhas. Os arquivos legados grandes não foram refatorados: AdicionarPreco tem 902 linhas; cadastro-preco.test.cjs passou a 502, conforme manifesto.

## Funções e responsabilidades

| Arquivo | Responsabilidade |
| --- | --- |
| components/leitor-totem.tsx | LeitorTotem isola conta/posto; ConteudoLeitor mantém foto e leitura; selecionar protege retorno tardio do picker; ler prepara arquivo antes do GPS e chama apenas leitura; interromperPedido cancela localmente; usarValor preenche formulário após revisar produto. |
| services/leituraTotem.ts | validarFoto confere metadados; prepararFotoWeb confere Blob real; formularioLeitura monta multipart/GPS sem cadastro/oferta; lerFotoTotem captura token/sinal; validarLeitura filtra quatro líquidos, precisão e link; comprovante aceita somente HTTPS nos hosts previstos. |
| services/leitura_totem.py | preparar_imagem valida bytes/formato/pixels antes do load, reduz e limpa metadados; _preco usa Decimal e literal monetário; normalizar_precos seleciona quatro combustíveis líquidos sem arredondar frações de centavo. |
| app/rotas/ia.py | Adaptadores preservam exceção/contrato da rota; guarda opcional passa a obedecer consentimento. |
| screens/AdicionarPreco/index.tsx | Liga sugestão e comprovante ao formulário, que continua exigindo cadastro separado. |
| services/cadastroPreco.ts | Encaminha foto_url opcional na transação já existente. |

Comentários de responsabilidade recebidos foram preservados; comentários locais explicam associação, encaminhamento e consentimento.

## Testes e comandos

Frontend, em C:/litro_de_ouro/front_end:

| Comando | Resultado | Evidência |
| --- | --- | --- |
| node tests/leitura-totem.test.cjs | exit 0, 8 casos | leitura-totem.test.cjs.log |
| node tests/leitor-totem-sessao.test.cjs | exit 0, 9 casos | leitor-totem-sessao.test.cjs.log |
| node node_modules/typescript/bin/tsc --noEmit | exit 0 | TYPESCRIPT.log |
| npm run lint | exit 0, sem erros/avisos de lint | LINT.log |
| node --test tests/*.test.cjs | exit 0, 113 aprovados, zero falhas | TESTES_FRONTEND.log |
| npx expo export --platform web | exit 0, saída local dist | EXPORT_WEB.log |

Os 113 incluem os 95 anteriores, os 17 recebidos e um caso local de comprovante; não somar execuções individuais ao total.

Backend: prefixo usado na raiz:

    docker compose -f compose.yaml -f docker/compose.testes-precos.yaml --env-file docker/local/.env exec -T

| Sufixo | Resultado | Evidência |
| --- | --- | --- |
| backend python -B -m unittest discover -s tests -p test_leitura_totem.py | exit 0, 8 casos | TESTES_IMAGEM.log |
| -e GEOFENCE_RAIO_M=500 backend python -B -m unittest discover -s tests -p test_ia.py | exit 5: assertivas executadas, mas zero casos unittest encontrados | TESTES_ROTA_IA.log |
| -e GEOFENCE_RAIO_M=500 -e PYTHONPATH=/app backend python -B tests/test_ia.py | exit 0, todas as assertivas aprovadas | TESTES_ROTA_DIRETO.log |
| backend python -B scripts/testar_offline.py | exit 0, nove scripts/suítes isolados | TESTES_BACKEND_OFFLINE.log |

O test_ia.py local é um script com assertivas no nível do módulo, não contém o wrapper unittest citado na preparação. A execução direta é a verificação válida; não foi criado wrapper artificial nem contado como um caso unittest. O runner offline soma 144 casos unittest em sete suítes, mais dois scripts de assertivas (IA e geofence). Os oito testes de imagem e oito do diagnóstico anterior já estão incluídos nesses 144.

## Runtime e efeitos

Docker estava desligado (pipe ausente mesmo com elevação). Foi iniciado Docker Desktop em janela oculta. Os containers existentes retornaram, com backend e banco saudáveis; labels confirmaram os mesmos arquivos Compose e override. O inicializador existente também foi restaurado pelo Docker e terminou exit 0 com mensagem: dados_locais_existentes_preservados. Não foi solicitado recriar base, volume ou aplicar migração. Não houve rebuild/recriação explícita de serviços: os fontes são montados no container existente. O raio 500 m foi usado somente nos processos de teste; a configuração de desenvolvimento do serviço não foi alterada.

Nenhuma chamada real a Gemini/Dropbox, foto pessoal ou cadastro real foi executado. Os testes de banco/provedores usam simuladores. A retomada dos serviços incluiu as verificações normais de saúde/inicialização, distintas dos testes offline.

## Evidências e limites

ALTERACOES.patch é incremental contra as cópias reais guardadas em base/, incluindo sete arquivos novos e cinco alterados; não é diff contra HEAD. git apply --reverse --check aprovou (PATCH_CHECK.log), sem executar reversão. MANIFESTO.json contém SHA-256 anterior/recebido/final, hash Git e linhas. recebidos/ guarda os sete fontes extraídos; os quatro documentos recebidos estão preservados nesta pasta.

Testes frontend: hooks/JSX/foco/picker/HTTP simulados; FormData/Blob e transformação Axios reais no teste de multipart. Backend: Pillow e Flask reais, imagens sintéticas, Gemini/Dropbox/banco simulados. O caso de pixels excessivos simula a abertura da imagem para confirmar recusa antes de load. Não há benchmark de memória/latência, React Native real ou renderização visual.

Exportação é compilação, não homologação de layout, acessibilidade, galeria ou aparelho. Não houve nova tentativa de prévia por computador. Acesso da API/login no celular permanece pendente de homologação, assim como GPS físico, provedores configurados e fotos de teste. Não foi configurada chave/modelo/Dropbox automaticamente.

Próxima homologação: acesso/login no aparelho; seleção/cancelamento; leitura com GPS real no raio normal; revisão e cadastro separado; conta/posto/saída e retorno tardio; comprovante desligado e depois ligado; falhas de GPS/arquivo/provedor/rede; tema, fonte, teclado e rolagem. Cancelar localmente não desfaz envio/upload já recebido pelo servidor.

Documentação consultada: [Expo ImagePicker SDK 58](https://docs.expo.dev/versions/v58.0.0/sdk/imagepicker/). Nesta sessão o acesso funcionou; a ausência de consulta na preparação externa não foi tratada como validação física.
