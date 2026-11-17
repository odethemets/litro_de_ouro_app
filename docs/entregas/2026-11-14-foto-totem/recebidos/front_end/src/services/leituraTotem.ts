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
