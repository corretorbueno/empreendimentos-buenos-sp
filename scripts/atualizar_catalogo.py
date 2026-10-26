

# -*- coding: utf-8 -*-
"""
ATUALIZADOR AUTOMÁTICO DO CATÁLOGO
Arquivo: atualizar_catalogo.py

O script atualiza empreendimentos.html diretamente.
Não exige marcadores especiais no HTML.
Não cria empreendimentos.json.
Cria um backup antes de alterar o HTML.

Instalação das dependências:
pip install requests beautifulsoup4

Execução:
python atualizar_catalogo.py
"""

import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURAÇÕES
# ============================================================

URL_CATALOGO = "https://www.econconstrutora.com.br/imoveis"

PASTA_SCRIPT = Path(__file__).resolve().parent
ARQUIVO_HTML = PASTA_SCRIPT / "empreendimentos.html"

TIMEOUT = 30
MINIMO_EMPREENDIMENTOS = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def limpar_texto(valor):
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def normalizar_nome(valor):
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(
        caractere
        for caractere in valor
        if not unicodedata.combining(caractere)
    )
    return re.sub(r"[^a-z0-9]+", " ", valor.lower()).strip()


def resolver_url(url, base):
    if not url:
        return ""

    url = limpar_texto(url)

    if url.startswith("data:"):
        return ""

    if url.startswith("//"):
        url = "https:" + url

    url = urljoin(base, url)

    if not url.startswith(("http://", "https://")):
        return ""

    if any(
        palavra in url.lower()
        for palavra in ("placeholder", "blank.gif", "spacer.gif")
    ):
        return ""

    return url


def obter_imagem(elemento, base_url):
    if elemento is None:
        return ""

    atributos = [
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
        "data-lazy",
    ]

    for atributo in atributos:
        valor = elemento.get(atributo)

        if valor:
            imagem = resolver_url(valor, base_url)

            if imagem:
                return imagem

    srcset = (
        elemento.get("srcset")
        or elemento.get("data-srcset")
        or ""
    )

    if srcset:
        opcoes = [
            parte.strip().split()[0]
            for parte in srcset.split(",")
            if parte.strip()
        ]

        # Normalmente a última opção é a de maior resolução.
        for opcao in reversed(opcoes):
            imagem = resolver_url(opcao, base_url)

            if imagem:
                return imagem

    return ""


def obter_nome_card(card, link):
    seletores = [
        "h1",
        "h2",
        "h3",
        "h4",
        "[class*='title']",
        "[class*='titulo']",
        "[class*='nome']",
        "[class*='name']",
    ]

    for seletor in seletores:
        elemento = card.select_one(seletor)

        if elemento:
            nome = limpar_texto(elemento.get_text(" ", strip=True))

            if nome:
                return nome

    imagem = card.select_one("img")

    if imagem and imagem.get("alt"):
        nome = limpar_texto(imagem.get("alt"))

        if nome:
            return nome

    return limpar_texto(link.get_text(" ", strip=True))


def identificar_status(texto):
    texto = normalizar_nome(texto)

    if "pronto para morar" in texto:
        return "Pronto para morar"

    if "em construcao" in texto or "em obras" in texto:
        return "Em obras"

    if "lancamento" in texto:
        return "Lançamento"

    return ""


# ============================================================
# BUSCA DOS EMPREENDIMENTOS NO SITE
# ============================================================

def extrair_catalogo():
    print("Acessando o catálogo da Econ Construtora...")

    resposta = requests.get(
        URL_CATALOGO,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")

    host_original = urlparse(URL_CATALOGO).netloc.lower()
    caminho_catalogo = urlparse(URL_CATALOGO).path.rstrip("/")

    resultados = {}

    # Procura links internos de páginas de empreendimentos.
    for link_elemento in soup.select("a[href]"):
        href = limpar_texto(link_elemento.get("href"))

        if not href:
            continue

        if href.startswith(("#", "javascript:", "mailto:")):
            continue

        link = urljoin(URL_CATALOGO, href)
        partes_url = urlparse(link)

        if partes_url.netloc.lower() != host_original:
            continue

        caminho = partes_url.path.rstrip("/")

        # Ignora o próprio catálogo.
        if caminho == caminho_catalogo:
            continue

        # Considera páginas abaixo de /imoveis/.
        if not caminho.startswith(caminho_catalogo + "/"):
            continue

        # Ignora URLs que parecem ser categorias ou paginação.
        if any(
            trecho in caminho.lower()
            for trecho in (
                "/categoria/",
                "/category/",
                "/tag/",
                "/author/",
                "/page/",
            )
        ):
            continue

        # Tenta subir no HTML para encontrar o card inteiro.
        card = link_elemento

        for _ in range(5):
            pai = card.parent

            if pai is None:
                break

            if getattr(pai, "name", "") in ("body", "html"):
                break

            card = pai

            if card.find(["h2", "h3", "h4"]) or card.find("img"):
                break

        nome = obter_nome_card(card, link_elemento)

        nome = re.sub(
            r"\b(saiba mais|ver detalhes|veja mais|conheça)\b.*$",
            "",
            nome,
            flags=re.IGNORECASE,
        ).strip(" -|")

        if len(nome) < 3 or len(nome) > 160:
            continue

        if normalizar_nome(nome) in {
            "saiba mais",
            "ver detalhes",
            "empreendimentos",
            "imoveis",
        }:
            continue

        imagem_elemento = card.select_one("img")
        imagem = obter_imagem(imagem_elemento, URL_CATALOGO)

        texto_card = limpar_texto(card.get_text(" ", strip=True))
        status = identificar_status(texto_card)

        item = {
            "nome": nome,
            "imagem": imagem,
            "link": link,
        }

        if status:
            item["status"] = status

        chave = normalizar_nome(nome)

        # Evita duplicatas e prefere o registro que tem imagem.
        anterior = resultados.get(chave)

        if (
            anterior is None
            or (not anterior.get("imagem") and imagem)
        ):
            resultados[chave] = item

    # Segunda tentativa com seletores comuns de cards.
    if len(resultados) < MINIMO_EMPREENDIMENTOS:
        seletores_cards = [
            "article",
            "[class*='imovel']",
            "[class*='empreendimento']",
            "[class*='property']",
            "[class*='project']",
            ".card",
        ]

        for seletor in seletores_cards:
            for card in soup.select(seletor):
                link_elemento = card.select_one("a[href]")

                if not link_elemento:
                    continue

                link = urljoin(
                    URL_CATALOGO,
                    limpar_texto(link_elemento.get("href")),
                )

                if urlparse(link).netloc.lower() != host_original:
                    continue

                nome = obter_nome_card(card, link_elemento)

                if len(nome) < 3 or len(nome) > 160:
                    continue

                imagem = obter_imagem(
                    card.select_one("img"),
                    URL_CATALOGO,
                )

                item = {
                    "nome": nome,
                    "imagem": imagem,
                    "link": link,
                }

                status = identificar_status(
                    card.get_text(" ", strip=True)
                )

                if status:
                    item["status"] = status

                chave = normalizar_nome(nome)

                if (
                    chave not in resultados
                    or (
                        not resultados[chave].get("imagem")
                        and imagem
                    )
                ):
                    resultados[chave] = item

    lista = list(resultados.values())

    if len(lista) < MINIMO_EMPREENDIMENTOS:
        raise RuntimeError(
            f"Foram encontrados somente {len(lista)} empreendimentos. "
            "A atualização foi cancelada para proteger o HTML existente. "
            "O site pode carregar seus dados por JavaScript ou ter mudado "
            "a estrutura da página."
        )

    return lista


# ============================================================
# LEITURA DO CATÁLOGO EXISTENTE NO HTML
# ============================================================

def localizar_array(html):
    """
    Localiza window.EMPREENDIMENTOS = [...] sem precisar de
    comentários ou marcadores especiais no HTML.
    """

    padroes = [
        r"(window\s*\.\s*EMPREENDIMENTOS\s*=\s*)(\[[\s\S]*?\])(\s*;?)",
        r"(window\s*\[\s*['\"]EMPREENDIMENTOS['\"]\s*\]\s*=\s*)(\[[\s\S]*?\])(\s*;?)",
    ]

    for padrao in padroes:
        resultado = re.search(padrao, html)

        if resultado:
            return resultado

    return None


def ler_catalogo_existente(html):
    resultado = localizar_array(html)

    if not resultado:
        raise RuntimeError(
            "Não encontrei window.EMPREENDIMENTOS = [...] no HTML. "
            "Nenhum arquivo foi alterado. Verifique se o arquivo "
            "empreendimentos.html é o correto."
        )

    conteudo = resultado.group(2)

    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as erro:
        raise RuntimeError(
            "O array window.EMPREENDIMENTOS existe, mas não está "
            "em formato JSON válido. Nenhum arquivo foi alterado."
        ) from erro

    if not isinstance(dados, list):
        raise RuntimeError(
            "O catálogo existente não é uma lista. "
            "Nenhum arquivo foi alterado."
        )

    return dados


# ============================================================
# MESCLAGEM DOS DADOS
# ============================================================

def mesclar_catalogo(existentes, encontrados):
    existentes_por_nome = {}

    for item in existentes:
        if not isinstance(item, dict):
            continue

        nome = (
            item.get("nome")
            or item.get("titulo")
            or item.get("empreendimento")
            or ""
        )

        chave = normalizar_nome(nome)

        if chave:
            existentes_por_nome[chave] = dict(item)

    resultado = []
    vistos = set()

    for encontrado in encontrados:
        nome = limpar_texto(encontrado.get("nome"))
        chave = normalizar_nome(nome)

        if not nome or chave in vistos:
            continue

        vistos.add(chave)

        antigo = existentes_por_nome.get(chave, {})
        item = dict(antigo)

        item["nome"] = nome

        # Atualiza o link quando a origem oferece um.
        if encontrado.get("link"):
            item["link"] = encontrado["link"]
        elif not item.get("link"):
            item["link"] = URL_CATALOGO

        # Não apaga uma imagem antiga se a extração não encontrar outra.
        if encontrado.get("imagem"):
            item["imagem"] = encontrado["imagem"]
        else:
            item.setdefault("imagem", "")

        if encontrado.get("status"):
            item["status"] = encontrado["status"]

        # Os demais campos já existentes são preservados.
        resultado.append(item)

    return resultado


# ============================================================
# ATUALIZAÇÃO SEGURA DO HTML
# ============================================================

def atualizar_html():
    print("=" * 55)
    print("ATUALIZADOR DO CATÁLOGO DE EMPREENDIMENTOS")
    print("=" * 55)

    print(f"\nArquivo HTML: {ARQUIVO_HTML}")

    if not ARQUIVO_HTML.exists():
        raise FileNotFoundError(
            "Não encontrei empreendimentos.html na mesma pasta "
            "do script atualizar_catalogo.py."
        )

    html_original = ARQUIVO_HTML.read_text(encoding="utf-8")

    existentes = ler_catalogo_existente(html_original)

    print(f"Registros atuais no HTML: {len(existentes)}")

    encontrados = extrair_catalogo()

    print(f"Registros encontrados no site: {len(encontrados)}")

    atualizados = mesclar_catalogo(existentes, encontrados)

    if len(atualizados) < MINIMO_EMPREENDIMENTOS:
        raise RuntimeError(
            "A lista final ficou pequena demais. "
            "O HTML não será alterado."
        )

    resultado = localizar_array(html_original)

    array_novo = json.dumps(
        atualizados,
        ensure_ascii=False,
        indent=2,
    )

    html_novo = (
        html_original[:resultado.start(2)]
        + array_novo
        + html_original[resultado.end(2):]
    )

    if html_novo == html_original:
        print("\nO catálogo já está atualizado.")
        print("Nenhuma alteração foi necessária.")
        return

    # Backup automático antes de escrever.
    horario = datetime.now().strftime("%Y%m%d_%H%M%S")

    arquivo_backup = ARQUIVO_HTML.with_name(
        f"{ARQUIVO_HTML.stem}_{horario}.bak.html"
    )

    arquivo_backup.write_text(
        html_original,
        encoding="utf-8",
    )

    # Grava em arquivo temporário e depois substitui o HTML.
    arquivo_temporario = ARQUIVO_HTML.with_name(
        ARQUIVO_HTML.name + ".tmp"
    )

    try:
        arquivo_temporario.write_text(
            html_novo,
            encoding="utf-8",
        )

        arquivo_temporario.replace(ARQUIVO_HTML)

    finally:
        if arquivo_temporario.exists():
            arquivo_temporario.unlink()

    print("\nATUALIZAÇÃO CONCLUÍDA!")
    print(f"Empreendimentos no HTML: {len(atualizados)}")
    print(f"Backup criado: {arquivo_backup.name}")
    print("O HTML foi atualizado automaticamente.")
    print("Nenhuma edição manual do HTML foi necessária.")


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    try:
        atualizar_html()

    except requests.RequestException as erro:
        print("\nERRO DE CONEXÃO:")
        print(erro)
        print("O HTML original foi mantido.")

        sys.exit(1)

    except Exception as erro:
        print("\nNÃO FOI POSSÍVEL ATUALIZAR:")
        print(erro)
        print("O HTML original foi mantido.")

        sys.exit(1)
