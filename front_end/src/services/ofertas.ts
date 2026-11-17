import type { PosicaoGps } from "../utils/localizacao";
import { COMBUSTIVEIS, type Combustivel } from "./catalogoPostos";

// Valida o GPS de cadastro e monta a confirmação explícita enviada à API.
export function payloadOferta(gps: PosicaoGps, agora = Date.now()) {
  if (!Number.isFinite(gps.latitude) || Math.abs(gps.latitude) > 90 ||
      !Number.isFinite(gps.longitude) || Math.abs(gps.longitude) > 180 ||
      (gps.latitude === 0 && gps.longitude === 0) ||
      !Number.isFinite(gps.precisaoM) || gps.precisaoM < 0 || gps.precisaoM > 150 ||
      !Number.isFinite(gps.obtidaEm) || gps.obtidaEm > agora + 5000 ||
      agora - gps.obtidaEm > 15000 || gps.simulada) {
    throw new Error("Precisamos de uma localização atual, precisa e não simulada.");
  }
  return { confirmado: true, latitude: gps.latitude, longitude: gps.longitude,
    precisao_m: gps.precisaoM, simulada: false };
}

// Só aceita sucesso para o mesmo posto/produto; resposta incompleta exige recarga.
export function validarConfirmacaoOferta(valor: unknown, postoId: number, codigo: Combustivel) {
  const r = valor as Record<string, unknown> | null;
  if (!r || r.posto_id !== postoId || r.codigo !== codigo || r.disponivel !== true ||
      !["manual", "osm"].includes(String(r.origem)) ||
      !COMBUSTIVEIS.some((p) => p.codigo === codigo)) {
    throw new Error("Confirmação incompleta. Atualize o catálogo antes de repetir.");
  }
}
