
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL_CATALOGO = "https://www.econconstrutora.com.br/imoveis"
ARQUIVO_HTML = Path("empreendimentos.html")
MARCADOR_INICIO = "<!-- CATALOGO_DATA_INICIO -->"
MARCADOR_FIM = "<!-- CATALOGO_DATA_FIM -->"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = texto.casefold()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def baixar_html(url):
    resposta = requests.get(
        url,
        headers=HEADERS,
        timeout=40,
    )
    resposta.raise_for_status()
    return resposta.text


def resolver_url_imagem(valor, base):
    if not valor:
        return ""

    valor = valor.strip()

    if valor.startswith(("data:", "blob:", "#")):
        return ""

    if valor.startswith("//"):
        valor = "https:" + valor

    url = urljoin(base, valor)
    partes = urlparse(url)

    if partes.scheme not in ("http", "https"):
        return ""

    if not partes.netloc:
        return ""

    return url


def imagens_da_tag(img, base):
    resultados = []

    # Prioriza atributos usados para carregamento tardio.
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
            valor = valor.split(",")[0].strip().split(" ")[0]

        url = resolver_url_imagem(valor, base)

        if url and url not in resultados:
            resultados.append(url)

    return resultados


def coletar_imagens_e_links():
    print(f"Acessando catálogo: {URL_CATALOGO}")

    soup = BeautifulSoup(
        baixar_html(URL_CATALOGO),
        "html.parser",
    )

    projetos = {}

    for titulo in soup.find_all(["h2", "h3", "h4", "h5"]):
        nome = " ".join(titulo.get_text(" ", strip=True).split())
        chave = normalizar(nome)

        if not chave or len(nome) > 120 or len(chave) < 3:
            continue

        if chave in {
            "empreendimentos",
            "imoveis",
            "lancamentos",
            "saiba mais",
            "ver mais",
        }:
            continue

        # Procura o card que contém o título e a imagem.
        bloco = titulo
        for _ in range(7):
            if bloco.parent is None:
                break

            bloco = bloco.parent

            if bloco.find("img") or bloco.find("a", href=True):
                break

        link_tag = titulo.find_parent("a", href=True)

        if link_tag is None:
            link_tag = bloco.find("a", href=True)

        link = ""
        if link_tag:
            link = urljoin(
                URL_CATALOGO,
                link_tag.get("href", ""),
            )

        imagem = ""

        for img in bloco.find_all("img"):
            texto_alt = normalizar(img.get("alt", ""))

            if any(
                palavra in texto_alt
                for palavra in ("logo", "icone", "icon", "avatar")
            ):
                continue

            candidatas = imagens_da_tag(img, URL_CATALOGO)

            if candidatas:
                imagem = candidatas[0]
                break

        anterior = projetos.get(chave, {})

        projetos[chave] = {
            "nome": nome,
            "imagem": imagem or anterior.get("imagem", ""),
            "link": link or anterior.get("link", ""),
        }

    # Algumas imagens só aparecem na página individual do empreendimento.
    for projeto in projetos.values():
        if projeto["imagem"] or not projeto["link"]:
            continue

        try:
            pagina = BeautifulSoup(
                baixar_html(projeto["link"]),
                "html.parser",
            )

            for seletor in (
                'meta[property="og:image"]',
                'meta[name="twitter:image"]',
            ):
                meta = pagina.select_one(seletor)

                if meta:
                    imagem = resolver_url_imagem(
                        meta.get("content", ""),
                        projeto["link"],
                    )

                    if imagem:
                        projeto["imagem"] = imagem
                        break

            if not projeto["imagem"]:
                for img in pagina.find_all("img"):
                    candidatas = imagens_da_tag(
                        img,
                        projeto["link"],
                    )

                    if candidatas:
                        projeto["imagem"] = candidatas[0]
                        break

        except requests.RequestException as erro:
            print(
                f"Aviso: não foi possível consultar "
                f"{projeto['nome']}: {erro}"
            )

    return projetos


def extrair_nome(objeto):
    correspondencia = re.search(
        r"""(?:["']nome["']|\bnome)\s*:\s*["']([^"']+)["']""",
        objeto,
        flags=re.IGNORECASE,
    )

    return correspondencia.group(1).strip() if correspondencia else ""


def atualizar_html(projetos):
    if not ARQUIVO_HTML.exists():
        raise RuntimeError(
            "empreendimentos.html não foi encontrado na raiz do repositório."
        )

    html_original = ARQUIVO_HTML.read_text(encoding="utf-8")

    inicio = html_original.find(MARCADOR_INICIO)
    fim = html_original.find(MARCADOR_FIM)

    if inicio < 0 or fim < 0 or fim <= inicio:
        raise RuntimeError(
            "Os marcadores CATALOGO_DATA_INICIO e "
            "CATALOGO_DATA_FIM não foram encontrados no HTML. "
            "Nenhuma alteração foi feita."
        )

    posicao_dados = inicio + len(MARCADOR_INICIO)
    bloco = html_original[posicao_dados:fim]

    # Este formato espera um objeto por empreendimento dentro do bloco.
    objetos = list(re.finditer(r"\{[^{}]*\}", bloco, re.DOTALL))

    if not objetos:
        raise RuntimeError(
            "Não encontrei objetos de empreendimentos dentro dos marcadores."
        )

    atualizados = 0
    sem_imagem = 0

    # Percorrer de trás para frente preserva as posições dos objetos restantes.
    for correspondencia in reversed(objetos):
        objeto = correspondencia.group(0)
        nome = extrair_nome(objeto)

        if not nome:
            continue

        campo_imagem = re.search(
            r"""(["']imagem["']\s*:\s*)(["'])(.*?)\2""",
            objeto,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if not campo_imagem:
            continue

        # Não substitui imagens que já estão preenchidas.
        if campo_imagem.group(3).strip():
            continue

        chave = normalizar(nome)
        projeto = projetos.get(chave)

        # Aceita correspondência parcial somente se for única.
        if not projeto or not projeto.get("imagem"):
            candidatos = [
                item
                for chave_site, item in projetos.items()
                if len(chave) >= 5
                and len(chave_site) >= 5
                and (
                    chave in chave_site
                    or chave_site in chave
                )
                and item.get("imagem")
            ]

            if len(candidatos) == 1:
                projeto = candidatos[0]

        if not projeto or not projeto.get("imagem"):
            sem_imagem += 1
            continue

        url = projeto["imagem"]

        # Mantém a sintaxe JavaScript/JSON com string entre aspas duplas.
        substituicao = (
            campo_imagem.group(1)
            + json.dumps(url, ensure_ascii=False)
        )

        novo_objeto = (
            objeto[:campo_imagem.start()]
            + substituicao
            + objeto[campo_imagem.end():]
        )

        bloco = (
            bloco[:correspondencia.start()]
            + novo_objeto
            + bloco[correspondencia.end():]
        )

        atualizados += 1

    if atualizados == 0:
        raise RuntimeError(
            "Nenhuma imagem foi atualizada. "
            "O HTML original foi preservado. "
            "Confira os nomes, os campos imagem e os dados retornados pela Econ."
        )

    html_novo = (
        html_original[:posicao_dados]
        + bloco
        + html_original[fim:]
    )

    # Confere que o documento não ficou vazio antes de gravar.
    if len(html_novo) < len(html_original) * 0.8:
        raise RuntimeError(
            "O HTML gerado ficou inesperadamente menor. "
            "Arquivo original preservado."
        )

    ARQUIVO_HTML.write_text(html_novo, encoding="utf-8")

    print(f"Imagens preenchidas: {atualizados}")
    print(f"Empreendimentos sem imagem correspondente: {sem_imagem}")
    print(f"HTML atualizado: {ARQUIVO_HTML}")


def main():
    projetos = coletar_imagens_e_links()

    total_com_imagem = sum(
        bool(projeto.get("imagem"))
        for projeto in projetos.values()
    )

    print(f"Empreendimentos identificados na Econ: {len(projetos)}")
    print(f"Com imagem encontrada: {total_com_imagem}")

    if not projetos or total_com_imagem == 0:
        raise RuntimeError(
            "Não foram encontradas imagens aproveitáveis. "
            "O HTML não será alterado."
        )

    atualizar_html(projetos)


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(1)

