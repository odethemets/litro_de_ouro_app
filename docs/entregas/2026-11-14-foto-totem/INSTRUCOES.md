# Bloco de foto do totem — aplicação e homologação

## Escopo

Conferir compatibilidade, aplicar os códigos recebidos, testar e devolver relatório/diff/resultados. O fluxo de foto já existia: esta entrega fortalece sessão/posto, ciclo do seletor, multipart, limites de imagem, precisão dos valores e revisão. Não substituir o projeto inteiro, não publicar, não aplicar migrações e não configurar provedores automaticamente.

Escolher foto não envia. Ler preços solicita arquivo/GPS e a rota de leitura. Usar um valor apenas preenche o formulário; cadastrar continua sendo outra ação, com a validação de proximidade e transação já existentes. A referência do mapa/feed não é alterada pelo leitor.

## Arquivos entregues

- CODIGOS_FRONTEND.md: versão completa de components/leitor-totem.tsx e novo services/leituraTotem.ts.
- CODIGOS_BACKEND.md: novo services/leitura_totem.py, seus testes e os trechos exatos de integração em app/rotas/ia.py.
- CODIGOS_TESTES_FRONTEND.md: dois arquivos de testes e seu helper independente.

Os três documentos e estas instruções são suficientes para reconstruir a entrega. O patch INTEGRACAO_IA.patch é opcional e representa o snapshot anterior disponível, não uma cópia recém-obtida do projeto Windows. Comparar o código local antes de aplicar qualquer substituição. Preservar mudanças posteriores e relatar adaptações.

Não é necessária dependência nova. Expo 58 e expo-image-picker já estão instalados. As tentativas de consultar a documentação versionada retornaram HTTP 403; foram conferidas as definições instaladas do SDK e os tipos do ImagePicker. TypeScript/lint passaram nessa cópia. Não houve migração para Expo Router; preservar a navegação atual.

Aplicar helper e integração do backend na mesma rodada, antes de reiniciar o serviço, para não deixar um import sem seu arquivo. O serviço cliente reutiliza a função já existente services/ofertas.payloadOferta somente para validar GPS: ele não confirma disponibilidade nem envia o campo confirmado na leitura.

## Integração no cadastro de preço

O componente mantém as quatro props anteriores. Acrescentar a prop opcional permitidos ao uso já existente em AdicionarPreco, sem reescrever a tela grande:

```tsx
{posto && posto.tipo_posto !== "Eletroposto" ? (
  <LeitorTotem
    key={posto.id}
    postoId={posto.id}
    bloqueado={bloqueado}
    permitidos={produtosCadastro(posto).map((item) => item.codigo)}
    limparComprovante={() => definirFotoUrl(null)}
    usar={(combustivel, valor, comprovante) => {
      if (!produtosCadastro(posto).some((item) => item.codigo === combustivel)) {
        definirFalha(new FalhaCadastro("validacao", "O produto lido não está disponível para este posto."));
        return;
      }
      selecionarCodigo(combustivel);
      definirPreco(valor);
      definirFotoUrl(comprovante);
      definirFalha(null);
    }}
  />
) : null}
```

Preservar nomes equivalentes se foram refatorados localmente. Conferir os pontos do comprovante que já existiam no fluxo recebido:

1. Estado fotoUrl/definirFotoUrl e import de LeitorTotem na tela.
2. Ao trocar posto ou combustível manualmente, remover a associação antiga com definirFotoUrl(null).
3. A chamada envio.enviar recebe fotoUrl junto de posto/combustivel/textoPreco/token.
4. PedidoCadastro tem fotoUrl?: string | null; PayloadPreco tem foto_url?: string.
5. payloadCadastro inclui ...(pedido.fotoUrl ? { foto_url: pedido.fotoUrl } : {}).
6. Botão de remover comprovante limpa a associação; ele não promete excluir o arquivo do Dropbox.

Se algum desses pontos ainda não existe na versão local, acrescentar somente esse campo/encaminhamento, mantendo validações, idempotência, sessão, GPS e transação atuais. Não copiar uma versão antiga inteira de cadastroPreco.ts ou de AdicionarPreco.

## Regras preservadas e mudanças deliberadas

- OCR sugere apenas gasolina comum/aditivada, etanol e diesel, todos em R$/L. GNV e kWh continuam manuais; o leitor não reutiliza um valor de outro produto.
- O intervalo legado do OCR é R$ 1,00–25,00. O cadastro manual continua com seu intervalo próprio de R$ 0,01–25,00; nenhuma dessas regras é alterada silenciosamente.
- Frações de centavo não são arredondadas para formar uma sugestão. Um terceiro decimal zero que não muda o valor é aceito. Se não houver preço válido, continua retornando leitura vazia; o usuário pode usar o cadastro manual.
- Não extrair número de texto arbitrário: "preço 5,89" não vira 5,89. O formato monetário simples "R$ 5,89" continua aceito no backend.
- JPEG, PNG e WebP, até 8 MB e 24 megapixels. Formatos fora desse contrato são recusados; fotos HEIC precisam ser selecionadas em formato compatível. Não há conversor HEIC nesta entrega.
- JPEG usa draft antes de load quando suportado, a saída tem até 1600 px e não carrega EXIF/ICC. O limite de pixels é verificado antes da decodificação completa. Não houve benchmark de RAM/latência.
- Android: uma seleção recuperada sem contexto não é atribuída automaticamente a outro posto/conta; orientar nova seleção. Web: cancelamento que não resolve não mantém o leitor travado; a última seleção válida vence.
- Guardar comprovante continua desativado por padrão. Consentimento controla o campo enviado. Uma URL só é anexada quando houve opção ativa e o retorno é HTTPS de um dos hosts Dropbox já aceitos pelo backend. Link inválido não inutiliza os preços legíveis.
- Cancelamento e saída impedem aplicar resposta tardia, mas não desfazem leitura ou upload já recebido pelo servidor. Não há retentativa automática.
- Multipart não herda application/json: Content-Type fica a cargo do transporte. A versão instalada do Axios foi inspecionada e houve teste de transformação com FormData/Blob reais.

## Design e plataforma

Preservar Surface, AppButton e Notice para cores, espaçamentos e tema do aplicativo. Prévia da imagem com altura limitada, botões secundários para seleção/comprovante e ação primária para leitura. A revisão apresenta nome, preço e unidade antes do preenchimento. Não há animação pulsante nem nova navegação.

Não incluir câmera/permissões extras, SDK novo ou imagem em base64. O seletor existente continua usando a galeria. Os tipos instalados confirmam os campos file/fileSize/mimeType e as opções usadas. A validação real no Expo Go/navegadores permanece necessária.

## Comandos de verificação

Na pasta front_end:

```powershell
node tests/leitura-totem.test.cjs
node tests/leitor-totem-sessao.test.cjs
npx tsc --noEmit
npm run lint
node --test tests/*.test.cjs
npx expo export --platform web
```

Na raiz, depois de atualizar os fontes no runtime Docker local que está em uso:

```powershell
docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python -B -m unittest discover -s tests -p "test_leitura_totem.py"
docker compose -f compose.yaml --env-file docker/local/.env exec -T backend python -B -m unittest discover -s tests -p "test_ia.py"
```

Se o backend não monta os fontes, reconstruir/recriar somente esse serviço local para incluir o helper/patch, mantendo a mesma combinação atual de Compose/overrides e preservando banco/volumes. Não mudar portas ou raio neste bloco. Rodar também as suítes offline existentes, em seus processos isolados, preservando a cobertura anterior.

## Evidência desta preparação

- 8 testes de contratos frontend, com FormData/Blob reais e HTTP simulado: aprovados.
- 9 cenários de sessão/picker/GPS/estado com hooks/JSX simulados: aprovados; sem React Native real.
- 8 testes Python com Pillow real: aprovados; sem provedores/banco.
- 1 teste-wrapper existente da rota: aprovado; executa diversas assertivas com Flask/Pillow reais e SDK/banco/Dropbox simulados. Não contar essas assertivas como casos unittest separados.
- TypeScript e lint dos arquivos entregues: aprovados na cópia de compatibilidade, sem erros/avisos.
- Não houve chamada ao Gemini/Dropbox, envio de foto pessoal, escrita no banco ou publicação nesta preparação.
- Os fontes de contexto são snapshots anteriores e os contratos recebidos, não uma cópia atual completa do Windows. Não foi repetida a prévia visual, anteriormente bloqueada pela política do navegador.

## Teste real e retorno

Primeiro resolver/retestar o acesso da API e o login no celular. Sem isso a leitura real não pode ser homologada. Depois, com configuração dos provedores no backend:

1. Selecionar e cancelar imagem sem enviar; escolher outra e conferir posto/foto.
2. Ler imagem conhecida no posto de teste, com GPS real e limite normal de proximidade. Revisar os valores, usar um deles, conferir o formulário e só então cadastrar.
3. Verificar autor/data/preço registrado, atividade e avisos sem confundir OCR com voto de validação.
4. Testar GPS negado, arquivo inválido, provedor indisponível e resposta perdida; sem preenchimento automático indevido.
5. Testar troca de conta/posto, saída, seleção tardia e cadastro em andamento. A resposta anterior não pode aparecer na nova identidade.
6. Testar Dropbox primeiro desativado; depois ativado em foto de teste. Falha do comprovante não impede revisar preços e não anexa link inválido. Desativar não exclui upload anterior.
7. Conferir tema claro/escuro, fonte ampliada, galeria, teclado e rolagem no aparelho e na web. Não apresentar build como prova visual.

Devolver relatório, diff incremental incluindo arquivos novos, comandos/resultados, explicação das funções e adaptações locais. Separar testes simulados, imagem/Flask reais, provedor real e teste físico. Não publicar nem aplicar migrações.
