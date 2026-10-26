
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urldefrag

import requests
from bs4 import BeautifulSoup

URL_BASE = "https://www.econconstrutora.com.br"
ARQUIVO_HTML = Path("empreendimentos.html")
MARCADOR_INICIO = "<!-- CATALOGO_DATA_INICIO -->"
MARCADOR_FIM = "<!-- CATALOGO_DATA_FIM -->"

PAGINAS_CATALOGO = [
    f"{URL_BASE}/imoveis",
    f"{URL_BASE}/imoveis/zona-leste",
    f"{URL_BASE}/imoveis/zona-sul",
    f"{URL_BASE}/imoveis/zona-norte",
    f"{URL_BASE}/imoveis/zona-oeste",
    f"{URL_BASE}/imoveis/centro",
    f"{URL_BASE}/imoveis/grande-sp",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    )
}
SESSAO = requests.Session()
SESSAO.headers.update(HEADERS)


def texto_limpo(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(
        c for c in texto if not unicodedata.combining(c)
    ).casefold().strip()


def buscar_pagina(url):
    resposta = SESSAO.get(url, timeout=40)
    resposta.raise_for_status()
    return BeautifulSoup(resposta.text, "html.parser")


def obter_imagem(bloco):
    for imagem in bloco.find_all("img"):
        for atributo in ("src", "data-src", "data-lazy-src", "data-original"):
            valor = imagem.get(atributo)
            if valor and not valor.startswith("data:"):
                return urljoin(URL_BASE, valor)
        srcset = imagem.get("srcset") or imagem.get("data-srcset")
        if srcset:
            primeiro = srcset.split(",")[0].strip().split(" ")[0]
            if primeiro and not primeiro.startswith("data:"):
                return urljoin(URL_BASE, primeiro)
    return ""


def encontrar_projetos(soup, url_pagina):
    projetos = {}

    for ancora in soup.find_all("a", href=True):
        href = urljoin(url_pagina, ancora["href"])
        href, _ = urldefrag(href)
        if not href.startswith(URL_BASE):
            continue

        texto_link = texto_limpo(ancora.get_text(" ", strip=True))
        bloco = ancora

        for _ in range(5):
            if bloco.parent is None:
                break
            bloco = bloco.parent
            texto_bloco = texto_limpo(bloco.get_text(" ", strip=True))
            if bloco.find(["h2", "h3", "h4"]) and len(texto_bloco) <= 1800:
                break

        titulo = ancora.find(["h2", "h3", "h4"]) or bloco.find(["h2", "h3", "h4"])
        nome = texto_limpo(
            titulo.get_text(" ", strip=True) if titulo else texto_link
        )
        if not nome or len(nome) > 100 or len(nome.split()) > 12:
            continue

        nome_normalizado = normalizar(nome)
        termos_invalidos = (
            "saiba mais", "ver mais", "ver todos", "conheca", "conheça",
        )


if __name__ == "__main__":
    main()
