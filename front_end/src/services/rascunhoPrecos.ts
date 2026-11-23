import { FalhaCadastro, precoCadastro } from "./cadastroPreco";
import { COMBUSTIVEIS, produto, type Combustivel } from "./catalogoPostos";
import type { ItemPrecoLote } from "./precosLote";

export interface RascunhoPreco extends ItemPrecoLote {
  selecionado: boolean;
}

export type SugestaoPreco = ItemPrecoLote;

function normalizar(texto: string) {
  return texto
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

// Cada parte precisa identificar produto e valor integralmente.
export function lerTextoPrecos(
  texto: string,
  permitidos: Combustivel[],
): SugestaoPreco[] {
  if (!texto.trim() || texto.length > 1200) {
    throw new FalhaCadastro(
      "validacao",
      "Escreva os preços em até 1.200 caracteres.",
    );
  }

  const partes = texto
    .trim()
    .split(/[;\n]+/)
    .map((p) => p.trim())
    .filter(Boolean);

  if (!partes.length || partes.length > 6) {
    throw new FalhaCadastro(
      "validacao",
      "Informe até seis produtos, sem repetições.",
    );
  }

  const vistos = new Set<Combustivel>();

  return partes.map((parte, indice) => {
    const dados = normalizar(parte).match(
      /^(.+?)\s*[:=]\s*(?:r\$\s*)?([0-9]+(?:[.,][0-9]{1,2})?)\s*(?:\/\s*(l|litro|m3|kwh))?$/,
    );

    const info =
      dados && COMBUSTIVEIS.find((p) => normalizar(p.nome) === dados[1].trim());

    if (!dados || !info || !permitidos.includes(info.codigo)) {
      throw new FalhaCadastro(
        "validacao",
        "Confira a linha " + (indice + 1) + ". Exemplo: Gasolina comum: 6,19.",
      );
    }

    if (vistos.has(info.codigo)) {
      throw new FalhaCadastro(
        "validacao",
        "O combustível " + info.nome + " está repetido.",
      );
    }

    const unidade = dados[3] === "litro" ? "l" : dados[3];

    if (unidade && unidade !== normalizar(info.unidade)) {
      throw new FalhaCadastro(
        "validacao",
        "Confira a unidade de " + info.nome + ": " + info.unidade + ".",
      );
    }

    const preco = precoCadastro(dados[2]);

    if (preco === null) {
      throw new FalhaCadastro(
        "validacao",
        "Confira o preço de " + info.nome + ".",
      );
    }

    vistos.add(info.codigo);

    return {
      codigo: info.codigo,
      textoPreco: preco,
      fotoUrl: null,
    };
  });
}

// Substituir campos ja preenchidos exige uma acao explicita.
export function mesclarSugestoes(
  atual: RascunhoPreco[],
  sugestoes: SugestaoPreco[],
  substituir = false,
): RascunhoPreco[] {
  const copia = atual.map((i) => ({ ...i }));
  const vistos = new Set<Combustivel>();

  for (const sugestao of sugestoes) {
    const item = copia.find((i) => i.codigo === sugestao.codigo);

    if (
      !item ||
      vistos.has(sugestao.codigo) ||
      precoCadastro(sugestao.textoPreco) === null
    ) {
      throw new FalhaCadastro(
        "validacao",
        "Revise os preços sugeridos antes de preencher.",
      );
    }

    vistos.add(sugestao.codigo);

    if (substituir || !item.textoPreco.trim()) {
      Object.assign(item, sugestao, { selecionado: true });
    }
  }

  return copia;
}

export function nomePreco(codigo: Combustivel) {
  return produto(codigo).nome + " · R$/" + produto(codigo).unidade;
}
