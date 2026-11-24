import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import type { CadastroLote } from "../../screens/AdicionarPreco/useCadastroLote";
import { precoCadastro, produtosCadastro } from "../../services/cadastroPreco";
import {
  dataPublicacao,
  precoFormatado,
  produto,
  type Combustivel,
  type PostoCatalogo,
} from "../../services/catalogoPostos";
import { nomePreco } from "../../services/rascunhoPrecos";
import { AppButton, AppField, Notice, Surface, useAppTheme } from "../design";

export function CamposPrecos({
  posto,
  form,
}: {
  posto: PostoCatalogo;
  form: CadastroLote;
}) {
  const { colors } = useAppTheme();
  const [focado, setFocado] = useState<Combustivel | null>(null);
  const permitidos = produtosCadastro(posto).map((p) => p.codigo);

  return (
    <Surface>
      <Text
        accessibilityRole="header"
        style={{
          color: colors.textPrimary,
          fontSize: 20,
          fontWeight: "800",
        }}
      >
        2. Selecione os preços
      </Text>
      <Notice>
        Digite um ou vários valores. Cada produto mantém sua unidade. Selecione
        apenas os que você observou.
      </Notice>

      {form.itens.map((item) => {
        const info = produto(item.codigo);
        const permitido = permitidos.includes(item.codigo);
        const oferta = posto.combustiveis.find((o) => o.codigo === item.codigo);

        return (
          <View
            key={item.codigo}
            style={{
              gap: 8,
              paddingVertical: 12,
              borderBottomWidth: 1,
              borderBottomColor: colors.border,
            }}
          >
            <Pressable
              accessibilityRole="checkbox"
              accessibilityLabel={"Registrar " + info.nome}
              accessibilityState={{
                checked: item.selecionado,
                disabled: form.bloqueado || (!permitido && !item.selecionado),
              }}
              disabled={form.bloqueado || (!permitido && !item.selecionado)}
              onPress={() =>
                form.alterar(item.codigo, { selecionado: !item.selecionado })
              }
              onFocus={() => setFocado(item.codigo)}
              onBlur={() => setFocado(null)}
              style={({ pressed }) => ({
                minHeight: 48,
                padding: 10,
                borderRadius: 12,
                borderWidth: 2,
                borderColor:
                  focado === item.codigo
                    ? colors.focus
                    : item.selecionado
                      ? colors.textPrimary
                      : colors.border,
                backgroundColor: item.selecionado
                  ? colors.selection
                  : colors.surface,
                opacity: pressed ? 0.75 : 1,
              })}
            >
              <Text
                style={{
                  color: colors.textPrimary,
                  fontWeight: "700",
                }}
              >
                {item.selecionado ? "✓ " : "○ "}
                {nomePreco(item.codigo)}
              </Text>
            </Pressable>

            <AppField
              label={"Preço de " + info.nome + " (R$/" + info.unidade + ")"}
              value={item.textoPreco}
              onChangeText={(textoPreco) =>
                form.alterar(item.codigo, { textoPreco })
              }
              editable={!form.bloqueado && permitido}
              keyboardType="decimal-pad"
              inputMode="decimal"
              placeholder="0,00"
              maxLength={8}
            />

            {!permitido ? (
              <Notice error>
                A oferta mudou. Remova este produto da seleção antes de
                continuar.
              </Notice>
            ) : null}

            {oferta?.disponivel === null ? (
              <Notice>
                A disponibilidade ainda não foi confirmada. Informe somente um
                preço observado neste posto.
              </Notice>
            ) : null}

            {oferta?.preco != null ? (
              <Notice>
                Último valor: {precoFormatado(oferta.preco)} / {info.unidade}.{" "}
                {dataPublicacao(oferta.atualizado_em)}
              </Notice>
            ) : null}

            {item.textoPreco.trim() &&
            precoCadastro(item.textoPreco) === null ? (
              <Notice error>
                Informe de R$ 0,01 a R$ 25,00, com até duas casas decimais.
              </Notice>
            ) : null}

            {item.fotoUrl ? (
              <AppButton
                label={"Remover comprovante de " + info.nome}
                secondary
                disabled={form.bloqueado}
                onPress={() => form.alterar(item.codigo, { fotoUrl: null })}
              />
            ) : null}
          </View>
        );
      })}

      {!form.itens.length ? (
        <Notice>
          Nenhum produto está disponível para registro neste cadastro.
        </Notice>
      ) : null}
    </Surface>
  );
}

export function TextoPrecos({ form }: { form: CadastroLote }) {
  return (
    <Surface>
      <AppField
        label="Preencher preços por texto"
        value={form.texto}
        onChangeText={form.setTexto}
        editable={!form.bloqueado}
        multiline
        numberOfLines={3}
        maxLength={1200}
        placeholder="Gasolina comum: 6,19; Etanol: 4,29"
        style={{ minHeight: 100, textAlignVertical: "top" }}
      />
      <Notice>
        Separe os produtos por ponto e vírgula ou quebra de linha. Exemplo: GNV:
        4,89 / m³.
      </Notice>
      <AppButton
        label="Conferir preços do texto"
        secondary
        disabled={form.bloqueado || !form.texto.trim()}
        onPress={form.lerTexto}
      />
    </Surface>
  );
}

export function SugestoesPrecos({ form }: { form: CadastroLote }) {
  if (!form.sugestoes) return null;

  const conflito = form.sugestoes.some((s) =>
    form.itens.find((i) => i.codigo === s.codigo)?.textoPreco.trim(),
  );

  return (
    <Surface>
      <Notice>
        Confira os valores sugeridos antes de levá-los aos campos.
      </Notice>

      {form.sugestoes.map((s) => (
        <Notice key={s.codigo}>
          {nomePreco(s.codigo)}: {precoFormatado(Number(s.textoPreco))}
          {s.fotoUrl ? " · com comprovante" : ""}
        </Notice>
      ))}

      <AppButton
        label="Preencher campos vazios"
        secondary
        disabled={form.bloqueado}
        onPress={() => form.preencher(false)}
      />

      {conflito ? (
        <>
          <Notice>
            Alguns campos já têm valores. Você pode mantê-los ou substituir
            somente os produtos sugeridos.
          </Notice>
          <AppButton
            label="Substituir valores desses produtos"
            secondary
            disabled={form.bloqueado}
            onPress={() => form.preencher(true)}
          />
        </>
      ) : null}

      <AppButton
        label="Descartar sugestões"
        secondary
        disabled={form.bloqueado}
        onPress={() => form.setSugestoes(null)}
      />
    </Surface>
  );
}

export function RevisaoPrecos({ form }: { form: CadastroLote }) {
  const { colors } = useAppTheme();
  const pedido = form.revisao;

  if (!pedido) return null;

  return (
    <Surface>
      <Text
        accessibilityRole="header"
        style={{
          color: colors.textPrimary,
          fontSize: 20,
          fontWeight: "800",
        }}
      >
        3. Confirme os preços
      </Text>

      <Notice>
        {pedido.posto.nome} · {pedido.posto.endereco}
      </Notice>

      {pedido.itens.map((i) => (
        <Notice key={i.codigo}>
          {produto(i.codigo).nome}: {precoFormatado(Number(i.textoPreco))} /{" "}
          {produto(i.codigo).unidade}
          {i.fotoUrl ? " · com comprovante" : ""}
        </Notice>
      ))}

      <Notice>
        {form.administrativo
          ? "Cadastro administrativo: todos os preços serão enviados juntos, sem GPS e sem Karma."
          : "Ao confirmar, sua localização será consultada novamente. Todos os preços selecionados serão enviados juntos."}
      </Notice>

      <AppButton
        label={
          "Confirmar " +
          pedido.itens.length +
          (pedido.itens.length === 1 ? " preço" : " preços")
        }
        busy={form.enviando}
        disabled={!form.permissaoConfirmada || form.enviando || form.incerto}
        onPress={() => void form.enviar()}
      />
      <AppButton
        label="Voltar para editar"
        secondary
        disabled={!form.permissaoConfirmada || form.enviando || form.incerto}
        onPress={() => form.setRevisao(null)}
      />
    </Surface>
  );
}
