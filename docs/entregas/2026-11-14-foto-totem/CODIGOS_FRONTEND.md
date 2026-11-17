# CODIGOS FRONTEND

Destinos relativos ao projeto. Aplicar conforme INSTRUCOES_CODEX_LOCAL.md.

## front_end/src/components/leitor-totem.tsx

```tsx
import * as ImagePicker from "expo-image-picker";
import { useCallback, useEffect, useRef, useState } from "react";
import { useFocusEffect } from "@react-navigation/native";
import { Image, Platform, View } from "react-native";

import { useAuth } from "../contexts/AuthContext";
import { COMBUSTIVEIS, precoFormatado, type Combustivel } from "../services/catalogoPostos";
import { formularioLeitura, lerFotoTotem, prepararFotoWeb, validarFoto, type LeituraTotem } from "../services/leituraTotem";
import { obterPosicao } from "../utils/localizacao";
import { AppButton, Notice, Surface } from "./design";

interface Props {
  postoId: number;
  bloqueado: boolean;
  permitidos?: Combustivel[];
  usar(codigo: Combustivel, preco: string, fotoUrl: string | null): void;
  limparComprovante(): void;
}

// Uma foto/resposta não pode pertencer à conta ou ao posto anterior.
export function LeitorTotem(props: Props) {
  const { token, status } = useAuth();
  if (!token || status !== "AUTHENTICATED") return null;
  return <ConteudoLeitor key={JSON.stringify([token, status, props.postoId])} {...props} token={token} />;
}

// O leitor sugere valores para o formulário; nunca chama a rota de cadastro de preço.
function ConteudoLeitor({ postoId, bloqueado, permitidos, usar, limparComprovante, token }: Props & { token: string }) {
  const [foto, setFoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [guardar, setGuardar] = useState(false);
  const [leitura, setLeitura] = useState<LeituraTotem | null>(null);
  const [operacao, setOperacao] = useState<AbortController | null>(null);
  const busy = !bloqueado && !!operacao && !operacao.signal.aborted;
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const consulta = useRef<AbortController | null>(null);
  const ativo = useRef(false);
  const selecao = useRef(0);
  const selecionando = useRef(false);
  const bloqueio = useRef(bloqueado);
  const limpar = useRef(limparComprovante);

  useEffect(() => { limpar.current = limparComprovante; }, [limparComprovante]);
  useEffect(() => {
    bloqueio.current = bloqueado;
    if (bloqueado) {
      consulta.current?.abort();
      consulta.current = null;
      selecao.current++;
      selecionando.current = false;
    }
  }, [bloqueado]);

  // Sair invalida picker e rede; o servidor pode ter recebido um envio já iniciado.
  useFocusEffect(useCallback(() => {
    ativo.current = true;
    setOperacao(null);
    setFoto(null);
    setLeitura(null);
    setGuardar(false);
    setErro("");
    setAviso("");
    if (!bloqueio.current) limpar.current();
    return () => {
      ativo.current = false;
      selecao.current++;
      selecionando.current = false;
      consulta.current?.abort();
      consulta.current = null;
    };
  }, []));

  // Lê o controlador no momento da interrupção, inclusive após uma espera do picker.
  function interromperPedido() {
    const atual = consulta.current;
    consulta.current = null;
    atual?.abort();
  }

  // Uma recuperação Android sem contexto não é vinculada automaticamente a este posto.
  useEffect(() => {
    if (Platform.OS !== "android") return;
    let atual = true;
    void ImagePicker.getPendingResultAsync().then((pendente) => {
      if (atual && ativo.current && pendente && "assets" in pendente && pendente.assets?.length) {
        setAviso("Uma seleção anterior foi interrompida. Escolha novamente a foto para este posto.");
      }
    }).catch(() => undefined);
    return () => { atual = false; };
  }, []);

  // Na web o cancelamento do picker pode não resolver: a última seleção vence.
  async function selecionar() {
    if (!ativo.current || bloqueio.current || consulta.current
      || (Platform.OS !== "web" && selecionando.current)) return;
    const id = ++selecao.current;
    selecionando.current = Platform.OS !== "web";
    setErro("");
    try {
      const resultado = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"], allowsEditing: false, quality: 0.8, exif: false, base64: false,
      });
      if (!ativo.current || bloqueio.current || selecao.current !== id || resultado.canceled) return;
      const imagem = resultado.assets[0];
      validarFoto(imagem);
      interromperPedido();
      setOperacao(null);
      limpar.current();
      setFoto(imagem);
      setLeitura(null);
      setAviso("");
    } catch (falha) {
      if (ativo.current && selecao.current === id) {
        setErro(falha instanceof Error ? falha.message : "Não foi possível selecionar a foto.");
      }
    } finally {
      if (selecao.current === id) selecionando.current = false;
    }
  }

  // Arquivo pronto → GPS atual → endpoint de leitura, com uma operação por vez.
  async function ler() {
    if (!foto || bloqueio.current || !ativo.current || consulta.current || selecionando.current) return;
    const atual = new AbortController();
    consulta.current = atual;
    setOperacao(atual);
    setErro("");
    setAviso("");
    setLeitura(null);
    let enviou = false;
    try {
      limpar.current();
      validarFoto(foto);
      const arquivo = Platform.OS === "web" ? await prepararFotoWeb(foto, atual.signal) : null;
      if (atual.signal.aborted || !ativo.current || bloqueio.current) return;
      const gps = await obterPosicao("registro");
      if (atual.signal.aborted || !ativo.current || bloqueio.current) return;
      const dados = formularioLeitura(postoId, foto, arquivo, gps, guardar);
      enviou = true;
      const resultado = await lerFotoTotem(dados, token, atual.signal, guardar);
      if (consulta.current !== atual || atual.signal.aborted || !ativo.current || bloqueio.current) return;
      setLeitura(resultado);
      setAviso(guardar && !resultado.fotoUrl
        ? "Preços lidos. O comprovante não foi confirmado e não será anexado."
        : "Revise os valores e escolha qual levar para o formulário. A leitura não cadastra preços.");
    } catch (falha) {
      if (atual.signal.aborted || consulta.current !== atual || !ativo.current) return;
      const resposta = (falha as { response?: { data?: { error?: unknown } } } | null)?.response;
      setErro(typeof resposta?.data?.error === "string" ? resposta.data.error
        : enviou ? "Não foi possível confirmar a leitura. A leitura não cadastra preços. O envio pode ter sido processado; confira antes de reenviar."
          : falha instanceof Error ? falha.message : "Não foi possível preparar a foto ou verificar a localização.");
    } finally {
      if (consulta.current === atual) {
        consulta.current = null;
        if (ativo.current) setOperacao(null);
      }
    }
  }

  // Usar um valor apenas preenche o cadastro, que continua com sua própria confirmação.
  function usarValor(codigo: Combustivel, preco: number) {
    if (bloqueio.current || !ativo.current || consulta.current || !leitura) return;
    if (permitidos && !permitidos.includes(codigo)) {
      setErro("Este produto não está disponível para cadastro neste posto.");
      return;
    }
    usar(codigo, preco.toFixed(2), leitura.fotoUrl);
    setAviso("Confira no formulário se combustível, unidade e preço estão corretos antes de cadastrar.");
  }

  return (
    <Surface>
      <Notice>Leitura de foto do totem · R$/L</Notice>
      <Notice>Leia gasolina comum, aditivada, etanol ou diesel. Informe GNV e recarga elétrica manualmente.</Notice>
      <Notice>A imagem será enviada ao serviço de IA. Somente os valores que você revisar serão levados ao formulário.</Notice>
      <AppButton label={foto ? "Escolher outra foto" : "Escolher foto do totem"} secondary
        disabled={busy || bloqueado} onPress={() => void selecionar()} />
      {foto ? (
        <>
          <Image source={{ uri: foto.uri }} accessibilityLabel="Foto selecionada para este posto"
            style={{ width: "100%", height: 200 }} resizeMode="contain" />
          <AppButton label={guardar ? "Salvar comprovante: ativado" : "Salvar comprovante: desativado"}
            secondary selected={guardar} disabled={busy || bloqueado} onPress={() => {
              setGuardar((valor) => !valor);
              setLeitura(null);
              setAviso("");
              limpar.current();
            }} />
          <Notice>Opcional: guardar uma cópia no Dropbox. Quem tiver o link poderá acessar a foto.
            Desativar não exclui cópias já enviadas.</Notice>
          <AppButton label="Ler preços da foto" busy={busy} disabled={bloqueado} onPress={() => void ler()} />
        </>
      ) : null}
      {busy ? <AppButton label="Cancelar leitura" secondary onPress={() => {
        interromperPedido();
        setOperacao(null);
        setAviso("Leitura cancelada nesta tela. O envio já iniciado pode ter sido processado. A leitura não cadastra preços.");
      }} /> : null}
      {erro ? <Notice error>{erro}</Notice> : null}
      {aviso ? <View accessibilityLiveRegion="polite"><Notice>{aviso}</Notice></View> : null}
      {leitura?.valores.map((v) => (
        <AppButton key={v.codigo} label={"Usar " + COMBUSTIVEIS.find((c) => c.codigo === v.codigo)!.nome
          + ": " + precoFormatado(v.preco) + " / L"} secondary
          disabled={busy || bloqueado || (permitidos !== undefined && !permitidos.includes(v.codigo))}
          onPress={() => usarValor(v.codigo, v.preco)} />
      ))}
    </Surface>
  );
}
```

## front_end/src/services/leituraTotem.ts

```typescript
import type { ImagePickerAsset } from "expo-image-picker";
import type { PosicaoGps } from "../utils/localizacao";
import { api } from "./API";
import { COMBUSTIVEIS, type Combustivel } from "./catalogoPostos";
import { payloadOferta } from "./ofertas";

export const LIMITE_FOTO = 8 * 1024 * 1024;
const TIPOS = ["image/jpeg", "image/png", "image/webp"];
const CODIGOS_FOTO = ["gasolina_comum", "gasolina_aditivada", "etanol", "diesel"];
const HOSTS_COMPROVANTE = ["dropbox.com", "www.dropbox.com", "dl.dropboxusercontent.com"];

export interface LeituraTotem {
  valores: { codigo: Combustivel; preco: number }[];
  fotoUrl: string | null;
  comprovanteSolicitado: boolean;
}

// Metadados ajudam na seleção; o servidor ainda valida os bytes de verdade.
export function validarFoto(foto: ImagePickerAsset) {
  if (!foto || typeof foto.uri !== "string" || !foto.uri.trim()
    || (foto.type != null && foto.type !== "image")
    || (foto.mimeType && !TIPOS.includes(foto.mimeType.toLowerCase()))
    || (foto.fileSize !== undefined && (!Number.isSafeInteger(foto.fileSize)
      || foto.fileSize <= 0 || foto.fileSize > LIMITE_FOTO))) {
    throw new Error("Escolha uma imagem JPEG, PNG ou WebP de até 8 MB.");
  }
  if (foto.width > 0 && foto.height > 0 && foto.width * foto.height > 24_000_000) {
    throw new Error("Escolha uma imagem de até 24 megapixels.");
  }
}

// Um link inválido não é anexado; os preços válidos podem continuar sendo revisados.
function comprovante(valor: unknown): string | null {
  if (typeof valor !== "string" || valor.length > 500 || /\s|[\u0000-\u001f\u007f]/.test(valor)) return null;
  try {
    const url = new URL(valor);
    return url.protocol === "https:" && HOSTS_COMPROVANTE.includes(url.hostname)
      && !url.username && !url.password ? valor : null;
  } catch { return null; }
}

// Valida os produtos/unidades sem estimar preço, arredondar ou aceitar GNV/kWh como litro.
export function validarLeitura(valor: unknown, guardar: boolean): LeituraTotem {
  const r = valor as { sucesso?: unknown; precos?: unknown; foto_url?: unknown } | null;
  if (!r || r.sucesso !== true || !r.precos || typeof r.precos !== "object" || Array.isArray(r.precos)) {
    throw new Error("A leitura não retornou preços válidos. Você pode informar o preço manualmente.");
  }
  const precos = r.precos as Record<string, unknown>;
  const valores = COMBUSTIVEIS.flatMap((c) => {
    const preco = precos[c.nome];
    if (!CODIGOS_FOTO.includes(c.codigo) || typeof preco !== "number" || !Number.isFinite(preco)
      || preco < 1 || preco > 25 || Math.abs(preco * 100 - Math.round(preco * 100)) > 1e-8) return [];
    return [{ codigo: c.codigo, preco }];
  });
  if (!valores.length) throw new Error("Nenhum preço legível foi confirmado. Informe o valor manualmente ou escolha outra foto.");
  return { valores, fotoUrl: guardar ? comprovante(r.foto_url) : null, comprovanteSolicitado: guardar };
}

// Prepara o arquivo antes do GPS para que a posição não envelheça durante a leitura local.
export async function prepararFotoWeb(foto: ImagePickerAsset, signal: AbortSignal): Promise<Blob> {
  validarFoto(foto);
  if (signal.aborted) throw new Error("Leitura cancelada.");
  let arquivo: Blob;
  if (foto.file) arquivo = foto.file;
  else {
    const resposta = await fetch(foto.uri, { signal });
    if (!resposta.ok) throw new Error("Não foi possível abrir a foto selecionada.");
    arquivo = await resposta.blob();
  }
  if (signal.aborted) throw new Error("Leitura cancelada.");
  if (!arquivo.size || arquivo.size > LIMITE_FOTO || (arquivo.type && !TIPOS.includes(arquivo.type))) {
    throw new Error("Escolha uma imagem JPEG, PNG ou WebP de até 8 MB.");
  }
  return arquivo;
}

// Reutiliza a validação de GPS de registro já aplicada à confirmação de oferta.
export function formularioLeitura(
  postoId: number, foto: ImagePickerAsset, arquivo: Blob | null, gps: PosicaoGps, guardar: boolean,
) {
  validarFoto(foto);
  if (!Number.isSafeInteger(postoId) || postoId <= 0 || postoId > 2147483647) {
    throw new Error("Escolha um posto válido antes de ler a foto.");
  }
  const posicao = payloadOferta(gps);
  const dados = new FormData();
  if (arquivo) dados.append("foto", arquivo, "totem");
  else dados.append("foto", { uri: foto.uri, name: "totem", type: foto.mimeType ?? "image/jpeg" } as unknown as Blob);
  dados.append("posto_id", String(postoId));
  dados.append("latitude", String(posicao.latitude));
  dados.append("longitude", String(posicao.longitude));
  dados.append("precisao_m", String(posicao.precisao_m));
  dados.append("simulada", "false");
  dados.append("guardar_comprovante", String(guardar));
  return dados;
}

// O endpoint só devolve sugestões; o cadastro continuará exigindo confirmação separada.
export async function lerFotoTotem(dados: FormData, token: string, signal: AbortSignal, guardar: boolean) {
  if (!token.trim() || signal.aborted) throw new Error("Entre novamente ou reinicie a leitura.");
  const { data } = await api.post("/ia/ler-totem", dados, {
    signal, timeout: 60000,
    headers: { Authorization: "Bearer " + token, "Content-Type": undefined },
  });
  if (signal.aborted) throw new Error("Leitura cancelada.");
  return validarLeitura(data, guardar);
}
```
