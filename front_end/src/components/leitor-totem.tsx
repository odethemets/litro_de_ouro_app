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
