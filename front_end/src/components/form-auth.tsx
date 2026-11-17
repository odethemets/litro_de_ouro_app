import { isAxiosError } from "axios";
import { useEffect, useRef, useState } from "react";
import { Pressable, Text, type TextInputProps } from "react-native";
import { AppField, useAppTheme } from "./design";

export const emailValido = (email: string) =>
  email.length <= 100 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

export const senhaValida = (senha: string) =>
  Boolean(senha.trim()) &&
  Array.from(senha).length >= 6 &&
  Array.from(senha).length <= 1024;

export function CampoSenha({
  label,
  ...props
}: TextInputProps & { label: string }) {
  const [mostrar, setMostrar] = useState(false);
  const { colors } = useAppTheme();

  return (
    <>
      <AppField
        {...props}
        label={label}
        secureTextEntry={!mostrar}
        autoCapitalize="none"
        autoCorrect={false}
      />

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={
          (mostrar ? "Ocultar " : "Mostrar ") + label.toLowerCase()
        }
        disabled={props.editable === false}
        onPress={() => setMostrar(!mostrar)}
        style={{
          minHeight: 48,
          justifyContent: "center",
          alignSelf: "flex-end",
          paddingHorizontal: 8,
        }}
      >
        <Text style={{ color: colors.textSecondary }}>
          {mostrar ? "Ocultar" : "Mostrar"} {label.toLowerCase()}
        </Text>
      </Pressable>
    </>
  );
}

export function useAcao(fallback: string) {
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState("");

  const pending = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  async function run(job: (signal: AbortSignal) => Promise<void>) {
    if (pending.current) return;

    const request = new AbortController();

    controller.current = request;
    pending.current = true;
    setBusy(true);
    setErro("");

    try {
      await job(request.signal);
    } catch (error: unknown) {
      if (!request.signal.aborted) {
        const body = isAxiosError<{ error?: string }>(error)
          ? error.response?.data
          : undefined;

        setErro(typeof body?.error === "string" ? body.error : fallback);
      }
    } finally {
      pending.current = false;

      if (!request.signal.aborted) {
        setBusy(false);
      }
    }
  }

  return { busy, erro, setErro, run };
}
