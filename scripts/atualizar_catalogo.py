

import json
import re
import time
import unicodedata
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURACAO
# ============================================================

BASE = "https://www.econconstrutora.com.br"
HTML_FILE = Path("empreendimentos.html")

MARCADOR_INICIO = "<!-- CATALOGO_DATA_INICIO -->"
MARCADOR_FIM = "<!-- CATALOGO_DATA_FIM -->"

PAGINAS_INICIAIS = [
    f"{BASE}/imoveis",
    f"{BASE}/imoveis/grande-sao-paulo",
    f"{BASE}/imoveis/zona-leste",
    f"{BASE}/imoveis/zona-sul",
    f"{BASE}/imoveis/zona-norte",
    f"{BASE}/imoveis/zona-oeste",
    f"{BASE}/imoveis/centro",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

TIMEOUT = 25
PAUSA_SEGUNDOS = 0.25
MAX_PAGINAS_LISTAGEM = 250

session = requests.Session()
session.headers.update(HEADERS)


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", texto).strip()


def url_limpa(url, origem=BASE):
    if not url:
        return ""

    url = urldefrag(urljoin(origem, url.strip()))[0]
    partes = urlparse(url)

    dominios_validos = {
        "econconstrutora.com.br",
        "www.econconstrutora.com.br",
    }

    if partes.scheme not in ("http", "https"):
        return ""

    if partes.netloc.lower() not in dominios_validos:
        return ""

    return url.rstrip("/")


def obter(url):
    try:
        resposta = session.get(url, timeout=TIMEOUT)
        resposta.raise_for_status()

        if "text/html" not in resposta.headers.get(
            "Content-Type", ""
        ).lower():
            return None

        return BeautifulSoup(resposta.text, "html.parser")

    except Exception as erro:
        print(f"[AVISO] Falha ao acessar {url}: {erro}")
        return None


def caminho_eh_listagem(url):
    caminho = urlparse(url).path.lower().rstrip("/")

    return (
        caminho == "/imoveis"
        or caminho.startswith("/imoveis/")
    )


def caminho_eh_detalhe(url):
    caminho = urlparse(url).path.lower().rstrip("/")

    # Aceita os dois formatos de endereco.
    return (
        caminho.startswith("/detalhes/")
        or caminho.startswith("/imovel/")
    )


def texto_no(elemento, seletores):
    for seletor in seletores:
        achado = elemento.select_one(seletor)

        if achado:
            texto = achado.get_text(" ", strip=True)

            if texto:
                return texto

    return ""


def imagem_do(elemento, pagina_url):
    img = elemento.select_one("img")

    if not img:
        return ""

    for atributo in (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "srcset",
    ):
        valor = img.get(atributo)

        if not valor:
            continue

        if atributo == "srcset":
            valor = valor.split(",")[0].strip().split(" ")[0]

        if valor.startswith("data:"):
            continue

        return urljoin(pagina_url, valor)

    return ""


def extrair_regiao_bairro(texto):
    partes = re.split(r"\s*[|•·]\s*", texto or "")

    if len(partes) >= 2:
        return partes[0].strip(), partes[1].strip()

    return (texto or "").strip(), ""


def achar_card(anchor):
    atual = anchor
    melhor = anchor

    for _ in range(7):
        if atual is None:
            break

        if getattr(atual, "name", None) in ("body", "html"):
            break

        texto = atual.get_text(" ", strip=True)

        if len(texto) > len(melhor.get_text(" ", strip=True)):
            melhor = atual

        tem_imagem = atual.select_one("img") is not None

        tem_info = re.search(
            r"(dorm|lançamento|lancamento|construção|"
            r"construcao|morar|bairro|zona)",
            texto,
            re.I,
        )

        if tem_imagem and tem_info:
            return atual

        atual = atual.parent

    return melhor


def extrair_cards_listagem(soup, pagina_url):
    projetos = []
    links_detalhe = set()

    for anchor in soup.find_all("a", href=True):
        href = url_limpa(anchor.get("href"), pagina_url)

        if not href:
            continue

        if caminho_eh_detalhe(href):
            links_detalhe.add(href)

        if not caminho_eh_detalhe(href):
            continue

        card = achar_card(anchor)
        texto_card = re.sub(
            r"\s+",
            " ",
            card.get_text(" ", strip=True),
        )

        nome = texto_no(
            card,
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "[class*='title']",
                "[class*='nome']",
            ],
        )

        if not nome:
            nome = anchor.get_text(" ", strip=True)

        nome = re.sub(r"\s+", " ", nome).strip()

        if not nome or len(nome) > 100:
            continue

        status = ""

        status_opcoes = [
            "Futuro Lançamento",
            "Futuro Lancamento",
            "Breve Lançamento",
            "Breve Lancamento",
            "Pronto para Morar",
            "Em Construção",
            "Em Construcao",
            "Lançamento",
            "Lancamento",
        ]

        texto_normalizado = normalizar(texto_card).lower()

        for opcao in status_opcoes:
            if normalizar(opcao).lower() in texto_normalizado:
                status = opcao
                break

        local_texto = ""

        for node in card.find_all(
            ["p", "span", "div", "li"]
        ):
            texto = node.get_text(" ", strip=True)

            if "|" in texto and len(texto) < 100:
                local_texto = texto
                break

        regiao, bairro = extrair_regiao_bairro(local_texto)

        dormitorios = ""
        match = re.search(
            r"(\d+(?:\s*e\s*\d+)?)\s*"
            r"dorm(?:itórios|itorios|s\.?)",
            texto_card,
            re.I,
        )

        if match:
            dormitorios = match.group(1).strip() + " dorm."

        projetos.append({
            "nome": nome,
            "regiao": regiao,
            "bairro": bairro,
            "status": status,
            "dormitorios": dormitorios,
            "imagem": imagem_do(card, pagina_url),
            "link": href,
        })

    return projetos, links_detalhe


def extrair_dados_detalhe(soup, url):
    nome = texto_no(
        soup,
        [
            "main h1",
            "h1",
            "[class*='title'] h1",
        ],
    )

    if not nome:
        meta = soup.select_one(
            "meta[property='og:title']"
        )

        if meta:
            nome = meta.get("content", "")

    nome = re.sub(
        r"\s*[-|]\s*Econ.*$",
        "",
        nome,
        flags=re.I,
    ).strip()

    texto = soup.get_text(" ", strip=True)
    texto_normalizado = normalizar(texto).lower()

    status = ""

    status_opcoes = [
        "Futuro Lançamento",
        "Futuro Lancamento",
        "Breve Lançamento",
        "Breve Lancamento",
        "Pronto para Morar",
        "Em Construção",
        "Em Construcao",
        "Lançamento",
        "Lancamento",
    ]

    for opcao in status_opcoes:
        if normalizar(opcao).lower() in texto_normalizado:
            status = opcao
            break

    dormitorios = ""
    match = re.search(
        r"(\d+(?:\s*e\s*\d+)?)\s*"
        r"dorm(?:itórios|itorios|s\.?)",
        texto,
        re.I,
    )

    if match:
        dormitorios = match.group(1).strip() + " dorm."

    imagem = ""
    og = soup.select_one("meta[property='og:image']")

    if og and og.get("content"):
        imagem = urljoin(url, og["content"])

    if not imagem:
        imagem = imagem_do(soup, url)

    regiao = ""
    bairro = ""

    for node in soup.find_all(
        ["p", "span", "div", "li"]
    ):
        texto_local = node.get_text(" ", strip=True)

        if "|" in texto_local and len(texto_local) < 100:
            regiao, bairro = extrair_regiao_bairro(
                texto_local
            )
            break

    return {
        "nome": nome,
        "regiao": regiao,
        "bairro": bairro,
        "status": status,
        "dormitorios": dormitorios,
        "imagem": imagem,
        "link": url,
    }


def descobrir_listagens():
    fila = deque(
        url_limpa(url)
        for url in PAGINAS_INICIAIS
    )

    visitadas = set()
    listagens = []
    detalhes = set()

    while fila and len(visitadas) < MAX_PAGINAS_LISTAGEM:
        url = fila.popleft()

        if not url or url in visitadas:
            continue

        if not caminho_eh_listagem(url):
            continue

        visitadas.add(url)
        soup = obter(url)

        if not soup:
            continue

        listagens.append((url, soup))

        _, links = extrair_cards_listagem(soup, url)
        detalhes.update(links)

        for anchor in soup.find_all("a", href=True):
            destino = url_limpa(anchor.get("href"), url)

            if not destino:
                continue

            if not caminho_eh_listagem(destino):
                continue

            if destino in visitadas:
                continue

            if "?" not in destino:
                fila.append(destino)

        print(
            f"[LISTAGEM] {url} | "
            f"links individuais: {len(detalhes)}"
        )

        time.sleep(PAUSA_SEGUNDOS)

    return listagens, detalhes


def deduplicar(projetos):
    por_nome = {}

    for projeto in projetos:
        nome = re.sub(
            r"\s+",
            " ",
            projeto.get("nome", ""),
        ).strip()

        if not nome:
            continue

        chave = normalizar(nome).lower()

        if chave not in por_nome:
            por_nome[chave] = projeto
            continue

        atual = por_nome[chave]

        campos = (
            "regiao",
            "bairro",
            "status",
            "dormitorios",
            "imagem",
            "link",
        )

        for campo in campos:
            if not atual.get(campo) and projeto.get(campo):
                atual[campo] = projeto[campo]

    return sorted(
        por_nome.values(),
        key=lambda item: normalizar(item["nome"]).lower(),
    )


def atualizar_html(projetos):
    if not HTML_FILE.exists():
        raise RuntimeError(
            f"Arquivo nao encontrado: {HTML_FILE}"
        )

    html = HTML_FILE.read_text(encoding="utf-8")

    if (
        MARCADOR_INICIO not in html
        or MARCADOR_FIM not in html
    ):
        raise RuntimeError(
            "Os marcadores do catalogo nao existem no HTML. "
            "Confira CATALOGO_DATA_INICIO e CATALOGO_DATA_FIM."
        )

    if not projetos:
        raise RuntimeError(
            "Nenhum empreendimento encontrado. "
            "O HTML nao sera alterado."
        )

    dados_json = json.dumps(
        projetos,
        ensure_ascii=False,
        indent=2,
    )

    bloco = (
        f"{MARCADOR_INICIO}\n"
        "<script>\n"
        f"window.EMPREENDIMENTOS = {dados_json};\n"
        "</script>\n"
        f"{MARCADOR_FIM}"
    )

    padrao = re.compile(
        re.escape(MARCADOR_INICIO)
        + r".*?"
        + re.escape(MARCADOR_FIM),
        re.DOTALL,
    )

    novo_html, alteracoes = padrao.subn(
        lambda _: bloco,
        html,
        count=1,
    )

    if alteracoes != 1:
        raise RuntimeError(
            "Nao foi possivel atualizar o bloco de dados."
        )

    # Grava o arquivo somente depois de validar tudo.
    HTML_FILE.write_text(
        novo_html,
        encoding="utf-8",
    )

    print(
        f"[OK] {len(projetos)} empreendimentos "
        f"gravados em {HTML_FILE}"
    )


def main():
    print("=== Atualizacao do catalogo Econ ===")

    listagens, urls_detalhes = descobrir_listagens()

    projetos = []

    # Aproveita primeiro os cards das paginas de listagem.
    for url, soup in listagens:
        cards, _ = extrair_cards_listagem(soup, url)
        projetos.extend(cards)

    print(
        f"[INFO] Paginas de listagem visitadas: "
        f"{len(listagens)}"
    )

    print(
        f"[INFO] Links individuais encontrados: "
        f"{len(urls_detalhes)}"
    )

    # Complementa os dados acessando as paginas individuais.
    urls = sorted(urls_detalhes)

    for indice, url in enumerate(urls, start=1):
        soup = obter(url)

        if soup:
            projeto = extrair_dados_detalhe(soup, url)

            if projeto.get("nome"):
                projetos.append(projeto)

        if indice % 20 == 0:
            print(
                f"[DETALHES] Processados "
                f"{indice}/{len(urls)}"
            )

        time.sleep(PAUSA_SEGUNDOS)

    projetos = deduplicar(projetos)

    print(
        f"[RESULTADO] Empreendimentos unicos: "
        f"{len(projetos)}"
    )

    if not projetos:
        raise RuntimeError(
            "Nenhum empreendimento foi identificado. "
            "O HTML existente foi preservado."
        )

    atualizar_html(projetos)


if __name__ == "__main__":
    main()

