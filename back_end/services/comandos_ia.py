"""Interpretação limitada a filtros que o catálogo realmente suporta."""
import re
import unicodedata

from services.catalogo_postos import validar_filtros


class BuscaNaoSuportada(ValueError):
    pass


def normalizar(texto):
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto.casefold())
        if not unicodedata.combining(c)
    )


PRODUTOS = (
    ("gasolina_aditivada", r"\b(?:gasolina\s+)?aditivada\b"),
    ("gasolina_comum", r"\bgasolina(?:\s+comum)?\b(?!\s+aditivada)"),
    ("etanol", r"\betanol\b|\balcool\b"),
    ("diesel", r"\bdiesel\b"),
    ("gnv", r"\bgnv\b|\bgas\s+natural\b"),
    (
        "recarga_eletrica",
        r"\beletric[oa]s?\b|\beletropostos?\b|\brecarga\b",
    ),
)

MARCAS = (
    ("Shell", r"\bshell\b"),
    ("Petrobras", r"\bpetrobras\b|\bbr\b"),
    ("Ipiranga", r"\bipiranga\b"),
    ("Ale", r"\bale\b"),
    ("Texaco", r"\btexaco\b"),
    ("Esso", r"\besso\b"),
)

PRECO = r"\bbarat[oa]s?\b|\bmenor\s+preco\b|\bem\s+conta\b"
PROXIMIDADE = r"\bproxim[oa]s?\b|\bperto\b|\bmenor\s+distancia\b"
TODOS = r"\btodos\s+(?:os\s+)?combustiveis\b"
QUALQUER = r"\b(?:qualquer|todas?(?:\s+as)?)\s+(?:bandeiras?|marcas?)\b"
DESCONHECIDA = r"\b(?:marca|bandeira)\s+nao\s+informada\b"

PALAVRAS = set((
    "quero queria gostaria desejo encontre encontrar procurar procure busca buscar "
    "busque mostre mostrar me um uma os as o a posto postos combustivel combustiveis "
    "que vendem vende tem tenham com preciso de da do e ou para abastecer por favor "
    "preco precos na no mais menos referencia em mim minha localizacao carregamento "
    "energia carro pode voce ver disponivel disponiveis ordene ordenar cidade"
).split())


def validar_objeto_filtros(objeto):
    chaves = {"combustiveis", "referencia", "marca", "ordenar"}

    if not isinstance(objeto, dict) or set(objeto) - chaves:
        raise ValueError("Filtros inválidos.")

    produtos = objeto.get("combustiveis", [])

    if (
        not isinstance(produtos, list)
        or len(produtos) > 6
        or any(not isinstance(c, str) for c in produtos)
    ):
        raise ValueError("Combustíveis inválidos.")

    for chave in ("referencia", "marca", "ordenar"):
        if chave in objeto and not isinstance(objeto[chave], str):
            raise ValueError("Filtros inválidos.")

    return validar_filtros(
        dict(objeto, combustiveis=",".join(produtos))
    )


def filtros_json(filtros):
    produtos, referencia, marca, ordenar = filtros

    return {
        "combustiveis": produtos,
        "referencia": referencia,
        "marca": marca or "",
        "ordenar": ordenar,
    }


def validar_escopo(texto):
    t = normalizar(texto)
    sem_marca = re.sub(DESCONHECIDA, "", t)

    if re.search(r"\b(?:nao|sem|exceto)\b", sem_marca):
        raise BuscaNaoSuportada(
            "Informe os combustíveis e a bandeira desejados. "
            "Exclusões por frase ainda não são suportadas."
        )

    if re.search(r"\b(?:s\s*10|s\s*500|premium|podium)\b", t):
        raise BuscaNaoSuportada(
            "O catálogo ainda não diferencia esses subtipos. "
            "Escolha uma categoria disponível nos filtros."
        )

    if re.search(
        r"\b(?:bairro|rua|avenida|rodovia|favoritos|aberto|abertos)\b"
        r"|\bbr\s*-\s*\d",
        t,
    ):
        raise BuscaNaoSuportada(
            "Esta busca aceita combustível, bandeira e ordenação. "
            "Endereços, favoritos e horários ainda não entram na busca por frase."
        )

    if re.search(
        r"(?:\b(?:(?:abaixo|acima)(?:\s+de)?|ate|menos\s+de|mais\s+de)"
        r"\s+(?:r\$\s*)?\d|r\$\s*\d)",
        t,
    ):
        raise BuscaNaoSuportada(
            "Limites numéricos por frase ainda não são suportados. "
            "Use a ordenação por menor preço."
        )

    escopo = re.sub(r"\bem conta\b|\breferencia em\b", "", t)
    local = re.search(r"\b(?:na cidade de|em)\s+(.+)", escopo)

    if local and not local.group(1).startswith("joao pessoa"):
        raise BuscaNaoSuportada(
            "O catálogo atual cobre João Pessoa. "
            "A busca por outras cidades ainda não está disponível."
        )

    perto = re.search(
        r"\b(?:perto|proxim[oa])\s+(?:de|do|da|a|ao)\s+(.+)",
        t,
    )

    if perto and not perto.group(1).startswith(
        ("mim", "minha localizacao")
    ):
        raise BuscaNaoSuportada(
            "A proximidade usa a localização do dispositivo. "
            "A busca ao redor de endereços ainda não está disponível."
        )


def pediu_proximidade(texto):
    return bool(re.search(PROXIMIDADE, normalizar(texto)))


def _produtos(texto):
    encontrados = sorted(
        (m.start(), codigo)
        for codigo, padrao in PRODUTOS
        for m in re.finditer(padrao, texto)
    )

    return list(dict.fromkeys(
        codigo for _, codigo in encontrados
    ))


def interpretar_comando(texto, atuais):
    validar_escopo(texto)
    t = normalizar(texto)

    referencia = re.search(
        r"\breferencia\s*(?:(?:de|em|para|e)\b|[:=])?\s*(.+)",
        t,
    )

    principal = t[:referencia.start()] if referencia else t
    produtos = _produtos(principal)
    ref_explicita = (
        _produtos(referencia.group(1)) if referencia else []
    )

    if referencia and len(ref_explicita) != 1:
        raise BuscaNaoSuportada(
            "Escolha um único combustível de referência."
        )

    todos = bool(re.search(TODOS, principal))
    marcas = [
        marca for marca, padrao in MARCAS
        if re.search(padrao, t)
    ]
    qualquer = bool(re.search(QUALQUER, t))
    desconhecida = bool(re.search(DESCONHECIDA, t))

    if len(marcas) + int(qualquer) + int(desconhecida) > 1:
        raise BuscaNaoSuportada(
            "Escolha uma bandeira por consulta."
        )

    if todos and produtos:
        raise BuscaNaoSuportada(
            "Escolha todos os combustíveis ou uma seleção específica."
        )

    barato = bool(re.search(PRECO, t))
    proximo = pediu_proximidade(t)

    if not (
        produtos or referencia or todos or marcas
        or qualquer or desconhecida or barato or proximo
    ):
        return None

    resto = t

    for padrao in [
        *(p for _, p in PRODUTOS),
        *(p for _, p in MARCAS),
        PRECO,
        PROXIMIDADE,
        TODOS,
        QUALQUER,
        DESCONHECIDA,
        r"\bjoao pessoa(?:\s*,?\s*pb)?\b",
    ]:
        resto = re.sub(padrao, " ", resto)

    if any(
        palavra not in PALAVRAS
        for palavra in re.findall(r"\w+", resto)
    ):
        return None

    selecionados = [] if todos else produtos or atuais[0]

    resultado = {
        "combustiveis": selecionados,
        "referencia": (
            ref_explicita[0] if ref_explicita
            else produtos[0] if produtos
            else atuais[1]
        ),
        "marca": (
            marcas[0] if marcas
            else "nao_informada" if desconhecida
            else "" if qualquer
            else atuais[2] or ""
        ),
        "ordenar": (
            "preco" if barato
            else "distancia" if proximo
            else atuais[3]
        ),
    }

    return filtros_json(validar_objeto_filtros(resultado))