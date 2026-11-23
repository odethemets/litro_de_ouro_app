import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useEffect, useRef, useState } from "react";
import { Image, Modal, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "../../contexts/AuthContext";
import { useFiltrosPostos } from "../../contexts/FiltrosPostosContext";
import { produto } from "../../services/catalogoPostos";
import { lerTokenAtivo } from "../../services/sessao";
import {
  consultarFotoServico,
  consultarSolicitacoes,
  decidirServico,
  falhaSolicitacao,
  type EstadoSolicitacao,
  type SolicitacaoServico,
} from "../../services/solicitacoesServicos";
import { AppButton, AppField, Notice, Surface, useAppTheme } from "../design";

interface Props {
  admin: boolean;
  fechar(): void;
}

export function PainelServicos(props: Props) {
  const { token, status } = useAuth();

  if (!token || status !== "AUTHENTICATED") return null;

  return (
    <ConteudoPainel
      key={JSON.stringify([token, props.admin])}
      {...props}
      token={token}
    />
  );
}

function ConteudoPainel({ admin, fechar, token }: Props & { token: string }) {
  const { colors } = useAppTheme();
  const { recarregar } = useFiltrosPostos();

  const [filtro, definirFiltro] = useState<{
    estado: EstadoSolicitacao | "todos";
  }>({
    estado: admin ? "pendente" : "todos",
  });

  const estado = filtro.estado;

  const [itens, definirItens] = useState<SolicitacaoServico[]>([]);
  const [antes, definirAntes] = useState<number | null>(null);
  const [selecionada, selecionar] = useState<SolicitacaoServico | null>(null);
  const [foto, definirFoto] = useState("");
  const [imagemPronta, definirImagemPronta] = useState(false);
  const [revisada, definirRevisada] = useState(false);
  const [motivo, definirMotivo] = useState("");
  const [busy, definirBusy] = useState(false);
  const [erro, definirErro] = useState("");
  const [incerta, definirIncerta] = useState(false);

  const pedido = useRef<AbortController | null>(null);
  const vivo = useRef(true);
  const fotoAtual = useRef<{ id: number; uri: string } | null>(null);

  const vigente = useCallback(
    (c: AbortController) =>
      vivo.current &&
      !c.signal.aborted &&
      pedido.current === c &&
      lerTokenAtivo() === token,
    [token],
  );

  useEffect(() => {
    vivo.current = true;

    return () => {
      vivo.current = false;
      fotoAtual.current = null;
      pedido.current?.abort();
    };
  }, []);

  useFocusEffect(
    useCallback(() => {
      const controller = new AbortController();

      pedido.current?.abort();
      pedido.current = controller;
      fotoAtual.current = null;

      definirBusy(true);
      definirErro("");
      definirItens([]);
      definirAntes(null);
      selecionar(null);
      definirFoto("");
      definirImagemPronta(false);
      definirRevisada(false);
      definirMotivo("");
      definirIncerta(false);

      void consultarSolicitacoes(token, controller.signal, admin, filtro.estado)
        .then((p) => {
          if (vigente(controller)) {
            definirItens(p.itens);
            definirAntes(p.antes_de);
          }
        })
        .catch((falha) => {
          if (vigente(controller)) {
            definirErro(
              falha instanceof Error ? falha.message : "Consulta indisponível.",
            );
          }
        })
        .finally(() => {
          if (vigente(controller)) {
            pedido.current = null;
            definirBusy(false);
          }
        });

      return () => {
        controller.abort();
        fotoAtual.current = null;
        pedido.current?.abort();
      };
    }, [token, admin, filtro, vigente]),
  );

  function iniciar() {
    if (pedido.current || busy || lerTokenAtivo() !== token) {
      return null;
    }

    const c = new AbortController();
    pedido.current = c;
    definirBusy(true);
    definirErro("");
    return c;
  }

  function terminar(c: AbortController) {
    if (vigente(c)) {
      pedido.current = null;
      definirBusy(false);
    }
  }

  async function mais() {
    if (!antes || incerta) return;

    const c = iniciar();
    if (!c) return;

    try {
      const p = await consultarSolicitacoes(
        token,
        c.signal,
        admin,
        estado,
        antes,
      );

      if (vigente(c)) {
        definirItens((atuais) => [...atuais, ...p.itens]);
        definirAntes(p.antes_de);
      }
    } catch (falha) {
      if (vigente(c)) {
        definirErro(
          falha instanceof Error ? falha.message : "Consulta indisponível.",
        );
      }
    } finally {
      terminar(c);
    }
  }

  async function abrirFoto(item: SolicitacaoServico) {
    if (incerta) return;

    const c = iniciar();
    if (!c) return;

    fotoAtual.current = null;
    selecionar(item);
    definirFoto("");
    definirImagemPronta(false);
    definirRevisada(false);
    definirMotivo("");
    definirIncerta(false);

    try {
      const uri = await consultarFotoServico(item.id, token, c.signal);

      if (vigente(c)) {
        fotoAtual.current = { id: item.id, uri };
        definirFoto(uri);
      }
    } catch (falha) {
      if (vigente(c)) {
        definirErro(
          falha instanceof Error ? falha.message : "Foto indisponível.",
        );
      }
    } finally {
      terminar(c);
    }
  }

  async function decidir(decisao: "aprovar" | "rejeitar") {
    if (!selecionada || incerta) return;

    const c = iniciar();
    if (!c) return;

    try {
      const resultado = await decidirServico(
        selecionada,
        decisao,
        motivo,
        !!foto && imagemPronta && revisada,
        token,
        c.signal,
      );

      if (vigente(c)) {
        definirItens((lista) =>
          lista.map((i) => (i.id === resultado.id ? resultado : i)),
        );

        fotoAtual.current = null;
        selecionar(resultado);
        definirFoto("");
        definirImagemPronta(false);
        definirRevisada(false);
        definirMotivo("");

        // Uma falha de recarga não converte decisão confirmada
        // em falha da escrita.
        if (resultado.estado === "aprovada") {
          try {
            recarregar();
          } catch {
            definirErro(
              "Decisão confirmada. Atualize o catálogo para ver a oferta.",
            );
          }
        }
      }
    } catch (falha) {
      if (vigente(c)) {
        const e = falhaSolicitacao(falha, true);
        definirErro(e.message);
        definirIncerta(e.incerta);
      }
    } finally {
      terminar(c);
    }
  }

  function imagemVigente(id: number, uri: string) {
    return (
      vivo.current &&
      lerTokenAtivo() === token &&
      fotoAtual.current?.id === id &&
      fotoAtual.current.uri === uri
    );
  }

  return (
    <Modal visible transparent animationType="slide" onRequestClose={fechar}>
      <View
        style={{
          flex: 1,
          backgroundColor: "rgba(0,0,0,.45)",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <SafeAreaView
          edges={["top", "bottom", "left", "right"]}
          style={{
            width: "100%",
            maxWidth: 850,
            flex: 1,
            backgroundColor: colors.background,
          }}
        >
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ padding: 20, gap: 14 }}
          >
            <Text
              accessibilityRole="header"
              style={{
                color: colors.textPrimary,
                fontSize: 24,
                fontWeight: "800",
              }}
            >
              {admin ? "Revisão de serviços" : "Minhas solicitações"}
            </Text>

            <Notice>
              {admin
                ? "Confira o posto, o serviço e a foto antes de decidir. A aprovação confirma a oferta, sem cadastrar preços."
                : "A presença do serviço só será liberada após a aprovação da equipe."}
            </Notice>

            <View
              style={{
                flexDirection: "row",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              {(["todos", "pendente", "aprovada", "rejeitada"] as const).map(
                (e) => (
                  <AppButton
                    key={e}
                    label={
                      {
                        todos: "Todas",
                        pendente: "Pendentes",
                        aprovada: "Aprovadas",
                        rejeitada: "Rejeitadas",
                      }[e]
                    }
                    secondary
                    selected={e === estado}
                    disabled={busy}
                    onPress={() => definirFiltro({ estado: e })}
                  />
                ),
              )}
            </View>

            <AppButton
              label="Atualizar solicitações"
              secondary
              disabled={busy}
              onPress={() => definirFiltro((f) => ({ ...f }))}
            />

            {busy ? <Notice>Consultando...</Notice> : null}
            {erro ? <Notice error>{erro}</Notice> : null}

            {!busy && !itens.length && !erro ? (
              <Notice>Nenhuma solicitação neste filtro.</Notice>
            ) : null}

            {itens.map((item) => (
              <Surface key={item.id}>
                <Text
                  style={{
                    color: colors.textPrimary,
                    fontWeight: "700",
                    fontSize: 18,
                  }}
                >
                  {item.posto_nome} · {produto(item.codigo).nome}
                </Text>

                <Notice>{item.posto_endereco}</Notice>

                <Notice>
                  Solicitação #{item.id} · {item.estado} ·{" "}
                  {new Date(item.criado_em).toLocaleString("pt-BR")}
                </Notice>

                {item.observacao ? <Notice>{item.observacao}</Notice> : null}

                {item.motivo ? <Notice>Motivo: {item.motivo}</Notice> : null}

                {admin ? (
                  <>
                    <Notice>
                      Proximidade verificada: {Math.round(item.distancia_m)} m.
                      Precisão informada: ±{Math.round(item.precisao_m)} m.
                    </Notice>

                    <AppButton
                      label="Abrir foto e revisar"
                      secondary
                      disabled={busy || incerta}
                      onPress={() => void abrirFoto(item)}
                    />

                    {selecionada?.id === item.id ? (
                      <>
                        {foto ? (
                          <Image
                            source={{ uri: foto }}
                            accessibilityLabel={
                              "Evidência de " +
                              produto(item.codigo).nome +
                              " em " +
                              item.posto_nome
                            }
                            style={{ width: "100%", height: 300 }}
                            resizeMode="contain"
                            onLoad={() => {
                              if (imagemVigente(item.id, foto)) {
                                definirImagemPronta(true);
                              }
                            }}
                            onError={() => {
                              if (imagemVigente(item.id, foto)) {
                                fotoAtual.current = null;
                                definirImagemPronta(false);
                                definirRevisada(false);
                                definirErro(
                                  "A foto não pôde ser exibida. Não aprove sem conferir a evidência.",
                                );
                              }
                            }}
                          />
                        ) : null}

                        {selecionada.pode_revisar ? (
                          <>
                            <AppButton
                              label={
                                revisada
                                  ? "Foto e posto conferidos"
                                  : "Confirmar que a foto comprova o serviço neste posto"
                              }
                              secondary
                              selected={revisada}
                              disabled={
                                busy || !foto || !imagemPronta || incerta
                              }
                              onPress={() => definirRevisada((v) => !v)}
                            />

                            <AppField
                              label="Motivo ou observação da revisão"
                              value={motivo}
                              maxLength={500}
                              multiline
                              editable={!busy && !incerta}
                              onChangeText={definirMotivo}
                            />

                            <AppButton
                              label="Aprovar presença do serviço"
                              disabled={
                                busy ||
                                !foto ||
                                !imagemPronta ||
                                !revisada ||
                                incerta
                              }
                              onPress={() => void decidir("aprovar")}
                            />

                            <AppButton
                              label="Rejeitar solicitação"
                              secondary
                              disabled={busy || !motivo.trim() || incerta}
                              onPress={() => void decidir("rejeitar")}
                            />
                          </>
                        ) : (
                          <Notice>
                            {selecionada.estado === "pendente"
                              ? "Sua própria solicitação precisa de outro administrador para revisão."
                              : "Esta solicitação já foi decidida."}
                          </Notice>
                        )}
                      </>
                    ) : null}
                  </>
                ) : null}
              </Surface>
            ))}

            {antes ? (
              <AppButton
                label="Carregar mais solicitações"
                secondary
                disabled={busy}
                onPress={() => void mais()}
              />
            ) : null}

            <AppButton label="Fechar" secondary onPress={fechar} />
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}
