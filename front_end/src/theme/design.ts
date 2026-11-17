export const design = {
  desktop: 1024,
  content: 1120,
  form: 480,
  radius: 20,
  fieldRadius: 14,
  touch: 48,
};
export const combustiveis = {
  gasolina_comum: { nome: "Gasolina comum", cor: "#1D4ED8", unidade: "L" },
  gasolina_aditivada: {
    nome: "Gasolina aditivada",
    cor: "#0891B2",
    unidade: "L",
  },
  etanol: { nome: "Etanol", cor: "#7C3AED", unidade: "L" },
  diesel: { nome: "Diesel", cor: "#374151", unidade: "L" },
  gnv: { nome: "GNV", cor: "#8B5E3C", unidade: "m³" },
  recarga_eletrica: {
    nome: "Recarga elétrica",
    cor: "#C026D3",
    unidade: "kWh",
  },
} as const;
