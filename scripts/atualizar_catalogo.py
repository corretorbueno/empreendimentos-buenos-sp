
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURACAO
# ============================================================

URL_BASE = "https://www.econconstrutora.com.br"
ARQUIVO_HTML = Path("empreendimentos.html")

MARCADOR_INICIO = "<!-- CATALOGO_DATA_INICIO -->"
MARCADOR_FIM = "<!-- CATALOGO_DATA_FIM -->"

PAGINAS_INICIAIS = [
    f"{URL_BASE}/imoveis",
    f"{URL_BASE}/imoveis/zona-leste",
    f"{URL_BASE}/imoveis/zona-sul",
    f"{URL_BASE}/imoveis/zona-norte",
    f"{URL_BASE}/imoveis/zona-oeste",
    f"{URL_BASE}/imoveis/centro",
    f"{URL_BASE}/imoveis/grande-sp",
]

SITEMAPS = [
    f"{URL_BASE}/sitemap.xml",
    f"{URL_BASE}/sitemap_index.xml",
    f"{URL_BASE}/sitemap-index.xml",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

SESSAO = requests.Session()
SESSAO.headers.update(HEADERS)
TIMEOUT = 35
PAUSA = 0.3


def limpar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(
        c for c in texto if not unicodedata.combining(c)
    ).casefold().strip()


def url_interna(url):
    url, _ = urldefrag(url)
    p = urlparse(url)
    host = p.netloc.lower()
    return (
        p.scheme in ("http", "https")
        and host in (
            "econconstrutora.com.br",
            "www.econconstrutora.com.br",
        )
    )


def requisitar(url):
    resposta = SESSAO.get(url, timeout=TIMEOUT)
    resposta.raise_for_status()
    return resposta


def ler_html(url):
    return BeautifulSoup(
        requisitar(url).text,
        "html.parser",
    )


def ler_sitemap(url_inicial):
    """Lê sitemaps comuns e índices de sitemaps."""
    urls = set()
    fila = deque([url_inicial])
    visitados = set()

    while fila:
        url = fila.popleft()

        if url in visitados:
            continue

        visitados.add(url)

        try:
            resposta = requisitar(url)
            raiz = ET.fromstring(resposta.content)

            for elemento in raiz.iter():
                if elemento.tag.split("}")[-1].lower() != "loc":
                    continue

                if not elemento.text:
                    continue

                link = elemento.text.strip()

                if not url_interna(link):
                    continue

                caminho = urlparse(link).path.lower()

                if "sitemap" in caminho and caminho.endswith(".xml"):
                    if link not in visitados:
                        fila.append(link)
                else:
                    urls.add(link)

        except (
            requests.RequestException,
            ET.ParseError,
            ValueError,
        ) as erro:
            print(f"Aviso: sitemap indisponivel: {url} ({erro})")

    return urls


def eh_detalhe(url):
    caminho = urlparse(url).path.strip("/").lower()

    # Links de detalhe conhecidos pelo formato /detalhes/slug.
    return caminho.startswith("detalhes/") and len(caminho.split("/")) >= 2


def descobrir_links_internos(soup, pagina):
    links = set()

    for ancora in soup.find_all("a", href=True):
        link = urljoin(pagina, ancora["href"])
        link, _ = urldefrag(link)

        if not url_interna(link):
            continue

        caminho = urlparse(link).path.lower()

        if re.search(
            r"\.(pdf|jpg|jpeg|png|webp|svg|zip|docx?)$",
            caminho,
        ):
            continue

        if any(
            termo in caminho
            for termo in (
                "/blog",
                "/noticias",
                "/contato",
                "/politica",
                "/privacidade",
            )
        ):
            continue

        links.add(link)

    return links


def obter_imagem(soup):
    og_image = soup.find("meta", property="og:image")

    if og_image and og_image.get("content"):
        return urljoin(URL_BASE, og_image["content"])

    for img in soup.find_all("img"):
        for atributo in (
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
        ):
            valor = img.get(atributo)

            if valor and not valor.startswith("data:"):
                return urljoin(URL_BASE, valor)

        srcset = img.get("srcset") or img.get("data-srcset")

        if srcset:
            valor = srcset.split(",")[0].strip().split(" ")[0]

            if valor and not valor.startswith("data:"):
                return urljoin(URL_BASE, valor)

    return ""


def extrair_detalhe(url):
    soup = ler_html(url)

    titulo = soup.find("h1")

    if titulo:
        nome = limpar(titulo.get_text(" ", strip=True))
    else:
        meta = soup.find("meta", property="og:title")
        nome = limpar(meta.get("content", "")) if meta else ""

    nome = re.sub(
        r"\s*[|–-]\s*Econ.*$",
        "",
        nome,
        flags=re.I,
    ).strip()

    if not nome:
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        nome = slug.replace("-", " ").title()

    texto = limpar(soup.get_text(" ", strip=True))
    texto_norm = normalizar(texto)

    status_opcoes = [
        "Futuro Lançamento",
        "Breve Lançamento",
        "Lançamento",
        "Em Construção",
        "Pronto para Morar",
    ]

    status = next(
        (
            item
            for item in status_opcoes
            if normalizar(item) in texto_norm
        ),
        "",
    )

    local_match = re.search(
        r"((?:Zona\s+(?:Leste|Sul|Norte|Oeste)|Centro|"
        r"Grande São Paulo|Santo André|Guarulhos|Diadema|"
        r"Osasco|São Bernardo do Campo|São Caetano do Sul|"
        r"Mauá|Suzano|Mogi das Cruzes|Itaquaquecetuba)"
        r"\s*\|\s*[^|]{2,90})",
        texto,
        re.I,
    )

    dormitorios_match = re.search(
        r"\b\d+(?:\s*e\s*\d+)?\s*dorms?\.?",
        texto,
        re.I,
    )

    meta_desc = soup.find("meta", attrs={"name": "description"})
    descricao = (
        limpar(meta_desc.get("content", ""))
        if meta_desc
        else texto[:500]
    )

    return {
        "nome": nome,
        "imagem": obter_imagem(soup),
        "link": url,
        "fonte": url,
        "descricao": descricao,
        "status": status,
        "localizacao": (
            limpar(local_match.group(1))
            if local_match
            else ""
        ),
        "dormitorios": (
            limpar(dormitorios_match.group(0))
            if dormitorios_match
            else ""
        ),
    }


def extrair_cards(soup, pagina):
    """Busca nomes e links diretamente nos cartoes do catalogo."""
    projetos = {}

    for ancora in soup.find_all("a", href=True):
        link = urljoin(pagina, ancora["href"])
        link, _ = urldefrag(link)

        if not url_interna(link) or not eh_detalhe(link):
            continue

        bloco = ancora

        for _ in range(7):
            if bloco.parent is None:
                break

            bloco = bloco.parent
            texto_bloco = limpar(bloco.get_text(" ", strip=True))

            if (
                bloco.find(["h2", "h3", "h4"])
                and len(texto_bloco) <= 2200
            ):
                break

        titulo = (
            ancora.find(["h2", "h3", "h4"])
            or bloco.find(["h2", "h3", "h4"])
        )

        nome = limpar(
            titulo.get_text(" ", strip=True)
            if titulo
            else ancora.get_text(" ", strip=True)
        )

        if (
            not nome
            or len(nome) > 120
            or len(nome.split()) > 14
        ):
            continue

        texto = limpar(bloco.get_text(" ", strip=True))
        texto_norm = normalizar(texto)

        status_opcoes = [
            "Futuro Lançamento",
            "Breve Lançamento",
            "Lançamento",
            "Em Construção",
            "Pronto para Morar",
        ]

        status = next(
            (
                item
                for item in status_opcoes
                if normalizar(item) in texto_norm
            ),
            "",
        )

        local_match = re.search(
            r"((?:Zona\s+(?:Leste|Sul|Norte|Oeste)|Centro|"
            r"Grande São Paulo|Santo André|Guarulhos|Diadema|"
            r"Osasco)\s*\|\s*[^|]{2,90})",
            texto,
            re.I,
        )

        dormitorios_match = re.search(
            r"\b\d+(?:\s*e\s*\d+)?\s*dorms?\.?",
            texto,
            re.I,
        )

        projetos[normalizar(nome)] = {
            "nome": nome,
            "imagem": obter_imagem(bloco),
            "link": link,
            "fonte": pagina,
            "descricao": texto[:500],
            "status": status,
            "localizacao": (
                limpar(local_match.group(1))
                if local_match
                else ""
            ),
            "dormitorios": (
                limpar(dormitorios_match.group(0))
                if dormitorios_match
                else ""
            ),
        }

    return projetos


def completar_campos(principal, complemento):
    for campo in (
        "imagem",
        "status",
        "localizacao",
        "dormitorios",
        "descricao",
    ):
        if not principal.get(campo) and complemento.get(campo):
            principal[campo] = complemento[campo]

    if eh_detalhe(complemento.get("link", "")):
        principal["link"] = complemento["link"]


def descobrir_urls_detalhes():
    """Combina sitemaps e links das páginas regionais."""
    urls = set()

    for sitemap in SITEMAPS:
        urls.update(ler_sitemap(sitemap))

    fila = deque(PAGINAS_INICIAIS)
    visitadas = set()

    # Limite para evitar percorrer indefinidamente todo o site.
    while fila and len(visitadas) < 150:
        pagina = fila.popleft()

        if pagina in visitadas:
            continue

        visitadas.add(pagina)

        try:
            soup = ler_html(pagina)
            links = descobrir_links_internos(soup, pagina)
            urls.update(links)

            # Enfileira páginas de catálogo/região, não cada link interno.
            for link in links:
                caminho = urlparse(link).path.lower().rstrip("/")

                if (
                    caminho == "/imoveis"
                    or caminho.startswith("/imoveis/")
                ) and link not in visitadas:
                    fila.append(link)

        except requests.RequestException as erro:
            print(f"Aviso: falha ao consultar {pagina}: {erro}")

        time.sleep(PAUSA)

    return sorted({url for url in urls if eh_detalhe(url)})


def atualizar_html(lista):
    if not ARQUIVO_HTML.exists():
        raise FileNotFoundError(
            f"Arquivo nao encontrado: {ARQUIVO_HTML}"
        )

    html = ARQUIVO_HTML.read_text(encoding="utf-8")

    if (
        html.count(MARCADOR_INICIO) != 1
        or html.count(MARCADOR_FIM) != 1
    ):
        raise RuntimeError(
            "O empreendimentos.html precisa ter exatamente uma "
            "ocorrencia de cada marcador:\n"
            f"{MARCADOR_INICIO}\n{MARCADOR_FIM}"
        )

    inicio = html.index(MARCADOR_INICIO)
    fim = html.index(MARCADOR_FIM) + len(MARCADOR_FIM)

    dados = json.dumps(
        lista,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", r"<\/")

    bloco = (
        MARCADOR_INICIO
        + "\n<script>\n"
        + "window.EMPREENDIMENTOS = "
        + dados
        + ";\n</script>\n"
        + MARCADOR_FIM
    )

    novo_html = html[:inicio] + bloco + html[fim:]
    ARQUIVO_HTML.write_text(novo_html, encoding="utf-8")


def main():
    print("=" * 60)
    print("ATUALIZACAO DO CATALOGO DE EMPREENDIMENTOS ECON")
    print("=" * 60)

    urls = descobrir_urls_detalhes()
    print(f"Links individuais encontrados: {len(urls)}")

    projetos = {}
    erros = []

    for numero, url in enumerate(urls, start=1):
        try:
            projeto = extrair_detalhe(url)
            chave = normalizar(projeto["nome"])

            if not chave:
                continue

            if chave in projetos:
                completar_campos(projetos[chave], projeto)
            else:
                projetos[chave] = projeto

        except requests.RequestException as erro:
            erros.append(f"{url}: {erro}")
            print(f"Aviso: erro ao ler {url}: {erro}")

        if numero % 10 == 0 or numero == len(urls):
            print(
                f"Processados: {numero}/{len(urls)} | "
                f"Empreendimentos unicos: {len(projetos)}"
            )

        time.sleep(PAUSA)

    # Completa os dados com os cartoes das paginas regionais.
    for pagina in PAGINAS_INICIAIS:
        try:
            soup = ler_html(pagina)
            cards = extrair_cards(soup, pagina)

            for chave, projeto in cards.items():
                if chave in projetos:
                    completar_campos(projetos[chave], projeto)
                else:
                    projetos[chave] = projeto

        except requests.RequestException as erro:
            erros.append(f"{pagina}: {erro}")
            print(f"Aviso: erro ao ler catalogo {pagina}: {erro}")

    lista = sorted(
        projetos.values(),
        key=lambda item: normalizar(item["nome"]),
    )

    # Protecao para nao substituir o HTML com uma coleta pequena.
    if len(lista) < 20:
        raise RuntimeError(
            f"Foram encontrados apenas {len(lista)} empreendimentos. "
            "O HTML nao foi alterado. Confira os logs e a estrutura "
            "atual do catalogo da Econ."
        )

    atualizar_html(lista)

    print("\nATUALIZACAO CONCLUIDA")
    print(f"Empreendimentos unicos: {len(lista)}")
    print(
        "Com imagem: "
        f"{sum(bool(p.get('imagem')) for p in lista)}"
    )
    print(
        "Com link individual: "
        f"{sum(eh_detalhe(p.get('link', '')) for p in lista)}"
    )
    print(f"HTML atualizado: {ARQUIVO_HTML}")

    if erros:
        print(f"Avisos de acesso: {len(erros)}")
        print("Veja as mensagens de aviso acima.")


if __name__ == "__main__":
    main()



if __name__ == "__main__":
    main()
