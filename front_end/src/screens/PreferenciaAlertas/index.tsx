import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import {
  AppButton,
  Notice,
  Page,
  Surface,
  useAppTheme,
} from "../../components/design";
import { useAcao } from "../../components/form-auth";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import {
  carregarPreferencias,
  INTERVALOS_ALERTAS,
  mensagemErroPreferencias,
  salvarPreferencias,
} from "../../services/alertas";
import { COMBUSTIVEIS, type Combustivel } from "../../services/catalogoPostos";
import type { FavoritosConta } from "../../services/participacao";

function Escolha({
  label,
  marcada,
  disabled,
  onPress,
}: {
  label: string;
  marcada: boolean;
  disabled: boolean;
  onPress(): void;
}) {
  const { colors } = useAppTheme();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: marcada, disabled }}
      aria-pressed={marcada}
      aria-disabled={disabled}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 48,
        padding: 14,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: marcada ? colors.textPrimary : colors.border,
        backgroundColor: marcada ? colors.selection : colors.surface,
        opacity: disabled ? 0.5 : pressed ? 0.75 : 1,
      })}
    >
      <Text style={{ color: colors.textPrimary, fontSize: 16 }}>
        {marcada ? "✓ " : "○ "}
        {label}
      </Text>
    </Pressable>
  );
}

function Formulario({
  inicial,
  recarregar,
}: {
  inicial: FavoritosConta;
  recarregar(): void;
}) {
  const [combustiveis, setCombustiveis] = useState(inicial.combustiveis);
  const [ativo, setAtivo] = useState(inicial.alertas.ativo);
  const [quedas, setQuedas] = useState(inicial.alertas.somente_quedas);
  const [intervalo, setIntervalo] = useState(inicial.alertas.intervalo_minutos);
  const [mensagem, setMensagem] = useState("");

  const { busy, erro, setErro, run } = useAcao(
    "Não foi possível confirmar as preferências. Recarregue antes de repetir.",
  );

  const bloqueado = busy || Boolean(erro);

  function alternar(codigo: Combustivel) {
    setMensagem("");

    setCombustiveis((atuais) =>
      atuais.includes(codigo)
        ? atuais.filter((item) => item !== codigo)
        : [...atuais, codigo],
    );
  }

  function salvar() {
    setMensagem("");

    void run(async (signal) => {
      try {
        const dados = await salvarPreferencias(
          {
            combustiveis,
            ativo,
            somente_quedas: quedas,
            intervalo_minutos: intervalo,
          },
          signal,
        );

        if (!signal.aborted) {
          setCombustiveis(dados.combustiveis);
          setAtivo(dados.alertas.ativo);
          setQuedas(dados.alertas.somente_quedas);
          setIntervalo(dados.alertas.intervalo_minutos);
          setMensagem("Preferências salvas.");
        }
      } catch (falha) {
        if (!signal.aborted) {
          setErro(mensagemErroPreferencias(falha));
        }
      }
    });
  }

  return (
    <>
      <Notice>As alterações passam a valer depois de salvar.</Notice>

      <Surface>
        <View accessibilityLiveRegion="polite" aria-live="polite">
          {mensagem ? <Notice>{mensagem}</Notice> : null}
        </View>

        {erro ? <Notice error>{erro}</Notice> : null}

        <AppButton
          label={
            mensagem ? "Preferências salvas" : "Salvar preferências de alertas"
          }
          busy={busy}
          disabled={Boolean(erro || mensagem)}
          onPress={salvar}
        />

        <AppButton
          label="Recarregar preferências salvas"
          secondary
          disabled={busy}
          onPress={recarregar}
        />
      </Surface>

      <Surface>
        <Notice>
          Os avisos combinam seus postos favoritos e os combustíveis escolhidos.
        </Notice>

        <Escolha
          label="Receber avisos de preços"
          marcada={ativo}
          disabled={bloqueado}
          onPress={() => {
            setMensagem("");
            setAtivo(!ativo);
          }}
        />

        {!inicial.postos.length ? (
          <Notice>Favorite pelo menos um posto para receber avisos.</Notice>
        ) : null}
      </Surface>

      <Surface>
        <Notice>Combustíveis favoritos</Notice>

        {COMBUSTIVEIS.map((item) => (
          <Escolha
            key={item.codigo}
            label={item.nome}
            marcada={combustiveis.includes(item.codigo)}
            disabled={bloqueado}
            onPress={() => alternar(item.codigo)}
          />
        ))}

        {!combustiveis.length ? (
          <Notice>
            Sem combustível selecionado, nenhum aviso será gerado.
          </Notice>
        ) : null}
      </Surface>

      <Surface>
        <Escolha
          label="Avisar somente quando o preço cair"
          marcada={quedas}
          disabled={bloqueado}
          onPress={() => {
            setMensagem("");
            setQuedas(!quedas);
          }}
        />

        <Notice>
          Com esta opção desativada, você acompanha todas as mudanças e o
          primeiro preço informado.
        </Notice>

        <Notice>
          Intervalo mínimo entre avisos do mesmo posto e combustível:
        </Notice>

        <View style={{ gap: 8 }}>
          {INTERVALOS_ALERTAS.map((valor) => (
            <Escolha
              key={valor}
              label={
                valor === 0
                  ? "Sem intervalo"
                  : valor === 1440
                    ? "24 horas"
                    : valor + " minutos"
              }
              marcada={intervalo === valor}
              disabled={bloqueado}
              onPress={() => {
                setMensagem("");
                setIntervalo(valor);
              }}
            />
          ))}
        </View>
      </Surface>

      <Notice>As alterações passam a valer depois de salvar.</Notice>

      <AppButton
        label="Salvar preferências de alertas"
        busy={busy}
        disabled={Boolean(erro)}
        onPress={salvar}
      />

      <AppButton
        label="Recarregar preferências salvas"
        secondary
        disabled={busy}
        onPress={recarregar}
      />
    </>
  );
}

export default function PreferenciasAlertas() {
  const consulta = useConsultaConta(carregarPreferencias);

  return (
    <Page
      title="Preferências de alertas"
      subtitle="Escolha os preços que deseja acompanhar."
    >
      {consulta.loading ? <Notice>Carregando preferências...</Notice> : null}

      {consulta.erro ? (
        <>
          <Notice error>Não foi possível carregar suas preferências.</Notice>

          <AppButton
            label="Tentar carregar preferências"
            onPress={consulta.atualizar}
          />
        </>
      ) : !consulta.loading && consulta.dados ? (
        <Formulario inicial={consulta.dados} recarregar={consulta.atualizar} />
      ) : null}
    </Page>
  );
}
