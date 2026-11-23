import { useFocusEffect } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import { useCallback, useRef, useState } from "react";
import { Image, Platform, View } from "react-native";

import { useAuth } from "../../contexts/AuthContext";
import { api } from "../../services/API";
import { produto, type Combustivel } from "../../services/catalogoPostos";
import { prepararFotoWeb, validarFoto } from "../../services/leituraTotem";
import { lerTokenAtivo } from "../../services/sessao";
import {
  criarEnvioSolicitacao,
  FalhaSolicitacao,
  novaChaveSolicitacao,
  type SolicitacaoServico,
} from "../../services/solicitacoesServicos";
import { obterPosicao } from "../../utils/localizacao";
import { AppButton, AppField, Notice } from "../design";
import { PainelServicos } from "./painel-servicos";

interface Props {
  postoId: number;
  codigo: Combustivel;
}

export function SolicitarServico(props: Props) {
  const { token, status, openAuth } = useAuth();

  if (!token || status !== "AUTHENTICATED") {
    return (
      <AppButton
        label="Entrar para sugerir serviço por foto"
        secondary
        onPress={() => openAuth("Login")}
      />
    );
  }

  return (
    <FormularioServico
      key={JSON.stringify([token, props.postoId, props.codigo])}
      {...props}
      token={token}
    />
  );
}

function FormularioServico({
  postoId,
  codigo,
  token,
}: Props & { token: string }) {
  const [aberto, abrir] = useState(false);
  const [foto, definirFoto] = useState<ImagePicker.ImagePickerAsset | null>(
    null,
  );
  const [observacao, definirObservacao] = useState("");
  const [presenca, definirPresenca] = useState(false);
  const [consentimento, definirConsentimento] = useState(false);
  const [selecionando, definirSelecao] = useState(false);
  const [busy, definirBusy] = useState(false);
  const [erro, definirErro] = useState("");
  const [incerta, definirIncerta] = useState(false);
  const [confirmada, definirConfirmada] = useState<SolicitacaoServico | null>(
    null,
  );
  const [historico, abrirHistorico] = useState(false);

  const chave = useRef(novaChaveSolicitacao());
  const operacao = useRef<AbortController | null>(null);
  const selecao = useRef(0);
  const escolhendo = useRef(false);
  const ativo = useRef(false);

  const [envio] = useState(() =>
    criarEnvioSolicitacao({
      tokenAtual: lerTokenAtivo,

      prepararFoto: (imagem, signal) =>
        Platform.OS === "web"
          ? prepararFotoWeb(imagem, signal)
          : Promise.resolve(null),

      obterGps: () => obterPosicao("registro"),

      postar: (id, dados, sessao, signal) =>
        api.post(`/postos/${id}/servicos/solicitacoes`, dados, {
          signal,
          timeout: 60000,
          headers: {
            Authorization: "Bearer " + sessao,
            "Content-Type": undefined,
          },
        }),
    }),
  );

  useFocusEffect(
    useCallback(() => {
      ativo.current = true;
      definirSelecao(false);
      escolhendo.current = false;

      if (operacao.current?.signal.aborted) {
        operacao.current = null;
        definirBusy(false);
        definirIncerta(true);
        definirErro(
          "O envio foi interrompido nesta tela. Confira suas solicitações antes de repetir.",
        );
      }

      return () => {
        ativo.current = false;
        selecao.current++;
        escolhendo.current = false;
        operacao.current?.abort();
      };
    }, []),
  );

  async function escolher() {
    if (
      !ativo.current ||
      operacao.current ||
      busy ||
      (Platform.OS !== "web" && escolhendo.current) ||
      incerta ||
      confirmada
    ) {
      return;
    }

    const numero = ++selecao.current;
    escolhendo.current = true;
    definirSelecao(true);
    definirErro("");

    try {
      // Deve ser chamado diretamente pelo toque no navegador mobile.
      const resultado = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsEditing: false,
        quality: 0.8,
        exif: false,
        base64: false,
      });

      if (!ativo.current || numero !== selecao.current || resultado.canceled) {
        return;
      }

      const imagem = resultado.assets[0];
      validarFoto(imagem);
      definirFoto(imagem);
      chave.current = novaChaveSolicitacao();
    } catch (falha) {
      if (ativo.current && numero === selecao.current) {
        definirErro(
          falha instanceof Error
            ? falha.message
            : "Não foi possível selecionar a foto.",
        );
      }
    } finally {
      if (numero === selecao.current) {
        escolhendo.current = false;

        if (ativo.current) {
          definirSelecao(false);
        }
      }
    }
  }

  async function enviar() {
    if (
      !foto ||
      busy ||
      escolhendo.current ||
      incerta ||
      confirmada ||
      operacao.current ||
      !ativo.current
    ) {
      return;
    }

    const atual = new AbortController();
    operacao.current = atual;
    definirBusy(true);
    definirErro("");

    try {
      const resultado = await envio.enviar({
        postoId,
        codigo,
        foto,
        observacao,
        consentimento,
        presencaObservada: presenca,
        chave: chave.current,
        token,
        signal: atual.signal,
      });

      if (
        !atual.signal.aborted &&
        ativo.current &&
        operacao.current === atual
      ) {
        definirConfirmada(resultado);
        definirFoto(null);
      }
    } catch (falha) {
      if (
        !atual.signal.aborted &&
        ativo.current &&
        operacao.current === atual
      ) {
        definirErro(
          falha instanceof Error
            ? falha.message
            : "Não foi possível enviar a solicitação.",
        );
        definirIncerta(falha instanceof FalhaSolicitacao && falha.incerta);
      }
    } finally {
      if (operacao.current === atual) {
        operacao.current = null;

        if (ativo.current) {
          definirBusy(false);
        }
      }
    }
  }

  const bloqueado = busy || selecionando || incerta || confirmada !== null;

  return (
    <View style={{ gap: 10 }}>
      {!aberto ? (
        <AppButton
          label="Sugerir presença por foto"
          secondary
          onPress={() => abrir(true)}
        />
      ) : (
        <>
          <Notice>
            Você encontrou {produto(codigo).nome} neste local? Envie uma foto do
            serviço e identifique o posto. A equipe revisará antes de liberar a
            oferta.
          </Notice>

          <Notice>
            Esteja no posto para enviar. Esta solicitação não informa preço nem
            concede Karma.
          </Notice>

          {!confirmada ? (
            <>
              <AppButton
                label={
                  foto ? "Escolher outra foto" : "Escolher foto do serviço"
                }
                secondary
                disabled={
                  busy ||
                  incerta ||
                  confirmada !== null ||
                  (Platform.OS !== "web" && selecionando)
                }
                onPress={() => void escolher()}
              />

              {foto ? (
                <Image
                  source={{ uri: foto.uri }}
                  accessibilityLabel="Foto escolhida como evidência do serviço"
                  style={{ width: "100%", height: 220 }}
                  resizeMode="contain"
                />
              ) : null}

              <AppField
                label="O que aparece na foto?"
                value={observacao}
                maxLength={500}
                multiline
                editable={!bloqueado}
                onChangeText={(texto) => {
                  definirObservacao(texto);
                  chave.current = novaChaveSolicitacao();
                }}
              />

              <AppButton
                secondary
                selected={presenca}
                disabled={bloqueado}
                label={
                  presenca
                    ? "Presença observada: confirmada"
                    : "Confirme que observou o serviço neste posto"
                }
                onPress={() => definirPresenca((v) => !v)}
              />

              <AppButton
                secondary
                selected={consentimento}
                disabled={bloqueado}
                label={
                  consentimento
                    ? "Envio e armazenamento da foto: autorizados"
                    : "Autorizar envio e armazenamento da foto para revisão"
                }
                onPress={() => definirConsentimento((v) => !v)}
              />

              <Notice>
                A foto ficará em armazenamento privado, acessível à equipe de
                revisão.
              </Notice>

              <AppButton
                label="Enviar para revisão"
                busy={busy}
                disabled={bloqueado || !foto || !presenca || !consentimento}
                onPress={() => void enviar()}
              />
            </>
          ) : (
            <Notice>
              Solicitação #{confirmada.id}:{" "}
              {confirmada.estado === "pendente"
                ? "aguardando revisão da equipe"
                : confirmada.estado}
              . Acompanhe em Minhas solicitações.
            </Notice>
          )}

          {erro ? <Notice error>{erro}</Notice> : null}

          <AppButton
            label="Conferir minhas solicitações"
            secondary
            disabled={busy || selecionando}
            onPress={() => abrirHistorico(true)}
          />

          {incerta ? (
            <AppButton
              label="Já conferi, preparar outro envio"
              secondary
              onPress={() => {
                definirIncerta(false);
                definirErro("");
                definirFoto(null);
                definirObservacao("");
                definirPresenca(false);
                definirConsentimento(false);
                chave.current = novaChaveSolicitacao();
              }}
            />
          ) : null}

          <AppButton
            label="Fechar solicitação"
            secondary
            disabled={busy || (Platform.OS !== "web" && selecionando)}
            onPress={() => {
              selecao.current++;
              escolhendo.current = false;
              definirSelecao(false);
              abrir(false);
            }}
          />
        </>
      )}

      {historico ? (
        <PainelServicos admin={false} fechar={() => abrirHistorico(false)} />
      ) : null}
    </View>
  );
}
