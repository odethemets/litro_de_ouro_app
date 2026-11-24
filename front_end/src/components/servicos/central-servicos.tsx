import { useCallback, useState } from "react";

import { useAuth } from "../../contexts/AuthContext";
import { useConsultaConta } from "../../hooks/useConsultaConta";
import { api } from "../../services/API";
import { lerAcessoServicos } from "../../services/solicitacoesServicos";
import { AppButton, Notice, Surface } from "../design";
import { PainelServicos } from "./painel-servicos";

export function CentralServicos() {
  const { token, status } = useAuth();

  if (!token || status !== "AUTHENTICATED") {
    return null;
  }

  return <ConteudoCentral key={token} token={token} />;
}

function ConteudoCentral({ token }: { token: string }) {
  const [painel, abrir] = useState<"minhas" | "admin" | null>(null);

  const carregar = useCallback(
    async (signal: AbortSignal) => {
      const { data } = await api.get("/admin/servicos/acesso", {
        signal,
        headers: {
          Authorization: "Bearer " + token,
        },
      });

      return lerAcessoServicos(data);
    },
    [token],
  );

  const consulta = useConsultaConta(carregar);

  return (
    <Surface>
      <Notice>Serviços dos postos</Notice>

      <AppButton
        label="Minhas solicitações de serviços"
        secondary
        onPress={() => abrir("minhas")}
      />

      {consulta.dados === true ? (
        <AppButton
          label="Revisar fotos e serviços"
          secondary
          onPress={() => abrir("admin")}
        />
      ) : null}

      {consulta.erro ? (
        <>
          <Notice error>Não foi possível conferir o acesso à revisão.</Notice>

          <AppButton
            label="Tentar novamente"
            secondary
            onPress={consulta.atualizar}
          />
        </>
      ) : null}

      {painel ? (
        <PainelServicos admin={painel === "admin"} fechar={() => abrir(null)} />
      ) : null}
    </Surface>
  );
}
