import Ionicons from "@expo/vector-icons/Ionicons";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import {
  AppButton,
  Notice,
  Page,
  Surface,
  useAppTheme,
} from "../../components/design";
import { useAuth } from "../../contexts/AuthContext";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import type { ContaPilha } from "../../routes/app.routes";
import { api } from "../../services/API";
import { iniciaisNome } from "../../services/atividadeConta";
import { validarPerfil } from "../../services/contratoAuth";
import { design } from "../../theme/design";

const carregarPerfil = async (signal: AbortSignal) =>
  validarPerfil((await api.get("/auth/perfil", { signal })).data);

type Props = NativeStackScreenProps<ContaPilha, "MeuPerfil">;
type Icone = React.ComponentProps<typeof Ionicons>["name"];

function Acesso({
  titulo,
  detalhe,
  icone,
  onPress,
}: {
  titulo: string;
  detalhe: string;
  icone: Icone;
  onPress(): void;
}) {
  const { colors } = useAppTheme();
  const [foco, setFoco] = useState(false);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={titulo}
      onPress={onPress}
      onFocus={() => setFoco(true)}
      onBlur={() => setFoco(false)}
      style={({ pressed }) => [
        styles.acesso,
        {
          backgroundColor: colors.surface,
          borderColor: foco ? colors.focus : colors.border,
          opacity: pressed ? 0.8 : 1,
        },
      ]}
    >
      <View style={[styles.icone, { backgroundColor: colors.selection }]}>
        <Ionicons
          name={icone}
          size={26}
          color={colors.textPrimary}
          accessible={false}
        />
      </View>

      <View style={{ flex: 1, gap: 4, minWidth: 0 }}>
        <Text
          style={{
            color: colors.textPrimary,
            fontSize: 18,
            fontWeight: "700",
          }}
        >
          {titulo}
        </Text>

        <Text
          style={{
            color: colors.textSecondary,
            fontSize: 14,
            lineHeight: 21,
          }}
        >
          {detalhe}
        </Text>
      </View>

      <Ionicons
        name="chevron-forward"
        size={20}
        color={colors.textSecondary}
        accessible={false}
      />
    </Pressable>
  );
}

export default function Conta({ navigation }: Props) {
  const { colors } = useAppTheme();
  const { signOut } = useAuth();
  const { width, fontScale } = useWindowDimensions();
  const consulta = useConsultaConta(carregarPerfil);

  const [confirmar, setConfirmar] = useState(false);
  const [saindo, setSaindo] = useState(false);
  const pendente = useRef(false);

  const perfil = consulta.dados;

  const sair = async () => {
    if (pendente.current) return;

    pendente.current = true;
    setSaindo(true);
    await signOut();
  };

  return (
    <Page title="Perfil" subtitle="Sua participação faz a diferença.">
      {consulta.loading ? (
        <View
          accessibilityRole="progressbar"
          accessibilityLabel="Atualizando perfil"
          style={styles.carregando}
        >
          <ActivityIndicator color={colors.textSecondary} />
          <Notice>Atualizando perfil...</Notice>
        </View>
      ) : null}

      {consulta.erro ? (
        <Surface>
          <Notice error>
            {perfil
              ? "Não foi possível atualizar. Exibindo os últimos dados recebidos."
              : "Não foi possível carregar o perfil."}
          </Notice>

          <AppButton
            label="Tentar novamente"
            disabled={consulta.loading}
            onPress={consulta.atualizar}
          />
        </Surface>
      ) : null}

      <View
        style={{
          flexDirection:
            width >= design.desktop && fontScale <= 1.3 ? "row" : "column",
          gap: 24,
          alignItems: "flex-start",
        }}
      >
        <View
          style={{
            flex: 1,
            width: "100%",
            minWidth: 0,
            gap: 16,
          }}
        >
          {perfil ? (
            <View style={styles.hero}>
              <View style={styles.identidade}>
                <View style={styles.avatar}>
                  <Text style={styles.iniciais}>
                    {iniciaisNome(perfil.nome)}
                  </Text>
                </View>

                <View style={{ gap: 6, flex: 1, minWidth: 0 }}>
                  <Text style={styles.nome}>{perfil.nome}</Text>
                  <Text style={styles.email}>{perfil.email}</Text>
                </View>
              </View>

              <View style={styles.selo}>
                <Text style={styles.seloTexto}>
                  {perfil.plano === "gratis"
                    ? "Plano grátis"
                    : "Plano: " + perfil.plano}
                </Text>
              </View>

              <View style={styles.saldo}>
                <Ionicons
                  name="trophy-outline"
                  size={30}
                  color="#FFC400"
                  accessible={false}
                />

                <Text style={styles.karma}>
                  {perfil.karma.toLocaleString("pt-BR")}
                </Text>

                <Text style={styles.legenda}>de Karma</Text>
              </View>

              <Text style={styles.email}>
                Membro desde {perfil.membro_desde}
              </Text>
            </View>
          ) : null}

          {perfil ? (
            <Notice>
              Seu Karma é atualizado a partir das contribuições confirmadas.
            </Notice>
          ) : null}
        </View>

        <View
          style={{
            flex: 1.2,
            width: "100%",
            minWidth: 0,
            gap: 12,
          }}
        >
          <Acesso
            titulo="Atividade pessoal"
            detalhe="Seu histórico de preços e consultas"
            icone="time-outline"
            onPress={() => navigation.navigate("AtividadePessoal")}
          />
          <Acesso
            titulo="Histórico de Karma"
            detalhe="Veja a origem e a data dos seus pontos"
            icone="trophy-outline"
            onPress={() => navigation.navigate("HistoricoKarma")}
          />

          <Acesso
            titulo="Ranking"
            detalhe="Contribuições da comunidade"
            icone="podium-outline"
            onPress={() => navigation.navigate("Ranking")}
          />
          <Acesso
            titulo="Favoritos"
            detalhe="Seus postos salvos neste dispositivo"
            icone="star-outline"
            onPress={() => navigation.navigate("Favoritos")}
          />

          <Acesso
            titulo="Configurações"
            detalhe="Senha, aparência e preferências"
            icone="settings-outline"
            onPress={() => navigation.navigate("Definicoes")}
          />

          <Acesso
            titulo="Notificações"
            detalhe="Consulte a disponibilidade dos alertas"
            icone="notifications-outline"
            onPress={() => navigation.navigate("Notificacoes")}
          />

          {confirmar ? (
            <Surface>
              <Notice>Deseja sair desta conta neste dispositivo?</Notice>

              <AppButton
                label="Confirmar saída"
                busy={saindo}
                onPress={() => {
                  void sair();
                }}
              />

              <AppButton
                label="Cancelar"
                secondary
                disabled={saindo}
                onPress={() => setConfirmar(false)}
              />
            </Surface>
          ) : (
            <AppButton
              label="Sair da conta"
              secondary
              onPress={() => setConfirmar(true)}
            />
          )}
        </View>
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  carregando: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  hero: {
    width: "100%",
    backgroundColor: "#171923",
    borderRadius: 24,
    padding: 24,
    gap: 20,
  },
  identidade: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 16,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: "#FFC400",
    justifyContent: "center",
    alignItems: "center",
  },
  iniciais: {
    fontSize: 30,
    fontWeight: "800",
    color: "#171923",
  },
  nome: {
    color: "#FFFFFF",
    fontSize: 24,
    fontWeight: "800",
  },
  email: {
    color: "#CBD1DD",
    fontSize: 14,
    lineHeight: 22,
    flexShrink: 1,
  },
  selo: {
    alignSelf: "flex-start",
    backgroundColor: "#303746",
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  seloTexto: {
    color: "#F3F4F6",
    fontSize: 14,
  },
  saldo: {
    borderTopWidth: 1,
    borderColor: "#495363",
    paddingTop: 20,
    gap: 4,
  },
  karma: {
    color: "#FFC400",
    fontSize: 52,
    fontWeight: "800",
  },
  legenda: {
    color: "#F3F4F6",
    fontSize: 18,
  },
  acesso: {
    borderWidth: 2,
    borderRadius: 20,
    padding: 16,
    minHeight: 96,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  icone: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
});
