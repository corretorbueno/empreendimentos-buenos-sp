
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

CATALOGO_URL = "https://www.econconstrutora.com.br/imoveis"
HTML_ARQUIVO = Path("empreendimentos.html")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

SESSAO = requests.Session()
SESSAO.headers.update(HEADERS)


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(
        c for c in texto if not unicodedata.combining(c)
    )
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def baixar_pagina(url):
    resposta = SESSAO.get(url, timeout=40)
    resposta.raise_for_status()
    return resposta.text


def resolver_url(valor, base):
    if not valor:
        return ""

    valor = valor.strip()

    if valor.startswith("//"):
        valor = "https:" + valor

    if valor.startswith(("data:", "blob:", "#")):
        return ""

    url = urljoin(base, valor)
    partes = urlparse(url)

    if partes.scheme not in ("http", "https"):
        return ""

    if not partes.netloc:
        return ""

    return url


def extrair_urls_img(img, base):
    urls = []

    for atributo in (
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
        "src",
        "data-srcset",
        "srcset",
    ):
        valor = img.get(atributo)

        if not valor:
            continue

        if "srcset" in atributo:
            opcoes = valor.split(",")
            if not opcoes:
                continue
            valor = opcoes[0].strip().split()[0]

        url = resolver_url(valor, base)

        if url and url not in urls:
            urls.append(url)

    return urls


def imagem_meta(soup, base):
    for seletor in (
        'meta[property="og:image"]',
        'meta[property="og:image:secure_url"]',
        'meta[name="twitter:image"]',
    ):
        meta = soup.select_one(seletor)

        if meta:
            url = resolver_url(meta.get("content", ""), base)
            if url:
                return url

    return ""


def coletar_imagens():
    print("Baixando HTML público da Econ...")
    html = baixar_pagina(CATALOGO_URL)
    soup = BeautifulSoup(html, "html.parser")

    projetos = {}

    # Primeiro: tenta coletar os cards que possuem título e imagem.
    for titulo in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5"]
    ):
        nome = " ".join(titulo.get_text(" ", strip=True).split())
        chave = normalizar(nome)

        if not chave or len(chave) < 3 or len(nome) > 120:
            continue

        if chave in {
            "empreendimentos",
            "imoveis",
            "lancamentos",
            "saiba mais",
            "ver mais",
        }:
            continue

        bloco = titulo

        for _ in range(8):
            if bloco.parent is None:
                break

            bloco = bloco.parent

            if bloco.find("img") and bloco.find("a", href=True):
                break

        link_tag = titulo.find_parent("a", href=True)

        if link_tag is None:
            link_tag = bloco.find("a", href=True)

        link = (
            urljoin(CATALOGO_URL, link_tag.get("href", ""))
            if link_tag
            else ""
        )

        imagem = ""

        for img in bloco.find_all("img"):
            alt = normalizar(img.get("alt", ""))

            if any(x in alt for x in ("logo", "icone", "avatar")):
                continue

            urls = extrair_urls_img(img, CATALOGO_URL)

            if urls:
                imagem = urls[0]
                break

        anterior = projetos.get(chave, {})

        projetos[chave] = {
            "nome": nome,
            "imagem": imagem or anterior.get("imagem", ""),
            "link": link or anterior.get("link", ""),
        }

    # Segundo: procura imagens nas páginas individuais dos projetos.
    for projeto in projetos.values():
        if projeto["imagem"] or not projeto["link"]:
            continue

        dominio = urlparse(projeto["link"]).netloc.lower()

        if not (
            dominio == "econconstrutora.com.br"
            or dominio.endswith(".econconstrutora.com.br")
        ):
            continue

        try:
            pagina = BeautifulSoup(
                baixar_pagina(projeto["link"]),
                "html.parser",
            )

            imagem = imagem_meta(pagina, projeto["link"])

            if not imagem:
                for img in pagina.find_all("img"):
                    alt = normalizar(img.get("alt", ""))

                    if any(
                        x in alt
                        for x in ("logo", "icone", "avatar")
                    ):
                        continue

                    urls = extrair_urls_img(img, projeto["link"])

                    if urls:
                        imagem = urls[0]
                        break

            projeto["imagem"] = imagem

        except requests.RequestException as erro:
            print(
                f"Aviso: erro ao abrir {projeto['nome']}: {erro}"
            )

    # Também captura dados estruturados JSON-LD, se existirem.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            dados = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue

        pilha = dados if isinstance(dados, list) else [dados]

        while pilha:
            item = pilha.pop()

            if isinstance(item, list):
                pilha.extend(item)
                continue

            if not isinstance(item, dict):
                continue

            if isinstance(item.get("@graph"), list):
                pilha.extend(item["@graph"])

            nome = item.get("name", "")
            imagem = item.get("image", "")

            if isinstance(imagem, list):
                imagem = imagem[0] if imagem else ""

            if isinstance(imagem, dict):
                imagem = imagem.get("url", "")

            if not nome or not imagem:
                continue

            chave = normalizar(str(nome))
            url = resolver_url(str(imagem), CATALOGO_URL)

            if chave in projetos and url:
                if not projetos[chave]["imagem"]:
                    projetos[chave]["imagem"] = url

    return projetos


def nome_do_objeto(objeto):
    # Reconhece nome: "Projeto" e "nome": "Projeto".
    match = re.search(
        r"""(?:["']nome["']|\bnome)\s*:\s*["']([^"']+)["']""",
        objeto,
        re.IGNORECASE,
    )

    return match.group(1).strip() if match else ""


def atualizar_html(projetos):
    if not HTML_ARQUIVO.exists():
        raise RuntimeError(
            "Não achei empreendimentos.html na raiz do repositório."
        )

    original = HTML_ARQUIVO.read_text(encoding="utf-8")

    # Não exige marcadores especiais: localiza objetos com nome e imagem.
    objetos = list(re.finditer(r"\{[^{}]*\}", original, re.DOTALL))

    alteracoes = 0
    sem_correspondencia = []

    for match in reversed(objetos):
        objeto = match.group(0)
        nome = nome_do_objeto(objeto)

        if not nome:
            continue

        campo = re.search(
            r"""(["']imagem["']\s*:\s*)(["'])(.*?)\2""",
            objeto,
            re.DOTALL | re.IGNORECASE,
        )

        if not campo:
            continue

        # Não sobrescreve imagens já existentes.
        if campo.group(3).strip():
            continue

        chave = normalizar(nome)
        projeto = projetos.get(chave)

        if not projeto or not projeto.get("imagem"):
            possiveis = [
                p for k, p in projetos.items()
                if len(k) >= 5
                and len(chave) >= 5
                and (k in chave or chave in k)
                and p.get("imagem")
            ]

            if len(possiveis) == 1:
                projeto = possiveis[0]

        if not projeto or not projeto.get("imagem"):
            sem_correspondencia.append(nome)
            continue

        # Usa JSON para escapar caracteres da URL com segurança.
        novo_campo = (
            campo.group(1)
            + json.dumps(projeto["imagem"], ensure_ascii=False)
        )

        novo_objeto = (
            objeto[:campo.start()]
            + novo_campo
            + objeto[campo.end():]
        )

        original = (
            original[:match.start()]
            + novo_objeto
            + original[match.end():]
        )

        alteracoes += 1

    if alteracoes == 0:
        raise RuntimeError(
            "Nenhuma imagem foi inserida. Confira se os objetos do HTML "
            "possuem campos nome e imagem e se a Econ retornou imagens. "
            "O arquivo não foi modificado."
        )

    HTML_ARQUIVO.write_text(original, encoding="utf-8")

    print(f"Imagens inseridas: {alteracoes}")
    print(f"Sem correspondência: {len(sem_correspondencia)}")

    for nome in sem_correspondencia[:30]:
        print(f"SEM IMAGEM: {nome}")

    print("empreendimentos.html salvo com sucesso.")


def main():
    projetos = coletar_imagens()

    quantidade = sum(
        bool(p.get("imagem"))
        for p in projetos.values()
    )

    print(f"Projetos detectados na Econ: {len(projetos)}")
    print(f"Projetos com imagem: {quantidade}")

    if quantidade == 0:
        raise RuntimeError(
            "A coleta não encontrou imagens. Nenhuma alteração foi feita."
        )

    atualizar_html(projetos)


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(1)

