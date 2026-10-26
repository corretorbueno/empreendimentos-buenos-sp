
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ARQUIVO_HTML = Path("empreendimentos.html")
URL_CATALOGO = "https://www.econconstrutora.com.br/imoveis"
DOMINIO_OFICIAL = "https://www.econconstrutora.com.br"

INICIO = "<!-- CATALOGO_DATA_INICIO -->"
FIM = "<!-- CATALOGO_DATA_FIM -->"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

TIMEOUT = 30
PAUSA = 0.4

session = requests.Session()
session.headers.update(HEADERS)


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def buscar_pagina(url):
    try:
        resposta = session.get(url, timeout=TIMEOUT)
        resposta.raise_for_status()
        resposta.encoding = resposta.apparent_encoding or "utf-8"
        print(f"[HTTP {resposta.status_code}] {url}")
        return resposta.text
    except requests.RequestException as erro:
        print(f"[ERRO DE ACESSO] {url}: {erro}")
        return ""


def url_imagem_valida(valor, base):
    if not valor:
        return ""

    valor = str(valor).strip().strip("\"'")
    if not valor or valor.startswith("data:"):
        return ""

    if valor.startswith("//"):
        valor = "https:" + valor

    url = urljoin(base, valor)

    partes = urlparse(url)
    if partes.scheme not in ("http", "https"):
        return ""

    caminho = partes.path.lower()
    extensoes = (
        ".jpg", ".jpeg", ".png", ".webp",
        ".avif", ".gif", ".jfif"
    )

    # URLs sem extensão também podem ser imagens servidas por CDN.
    if any(caminho.endswith(ext) for ext in extensoes):
        return url

    if any(p in caminho for p in (
        "/image/", "/images/", "/imagem/", "/media/",
        "/uploads/", "/upload/", "/storage/"
    )):
        return url

    if "?" in url and any(p in url.lower() for p in (
        "image", "img", "format=webp", "fm=webp"
    )):
        return url

    return ""


def extrair_srcset(valor, base):
    if not valor:
        return ""

    # Prefere a maior imagem declarada no srcset.
    opcoes = []
    for item in valor.split(","):
        partes = item.strip().split()
        if not partes:
            continue

        url = url_imagem_valida(partes[0], base)
        largura = 0

        if len(partes) > 1:
            match = re.search(r"(\d+)w", partes[1])
            if match:
                largura = int(match.group(1))

        if url:
            opcoes.append((largura, url))

    if not opcoes:
        return ""

    return max(opcoes, key=lambda x: x[0])[1]


def extrair_imagem_tag(img, base):
    # A ordem prioriza imagens de carregamento tardio e imagens responsivas.
    for atributo in (
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
        "data-full",
        "data-large-file",
        "src",
    ):
        url = url_imagem_valida(img.get(atributo), base)
        if url:
            return url

    for atributo in ("data-srcset", "srcset"):
        url = extrair_srcset(img.get(atributo), base)
        if url:
            return url

    # Algumas páginas guardam a imagem em background-image.
    estilo = img.get("style", "")
    match = re.search(r"url\(['\"]?(.*?)['\"]?\)", estilo)
    if match:
        url = url_imagem_valida(match.group(1), base)
        if url:
            return url

    return ""


def imagem_na_area(elemento, base):
    if elemento is None:
        return ""

    # Primeiro procura imagens dentro do cartão.
    for img in elemento.select("img"):
        url = extrair_imagem_tag(img, base)
        if url and not imagem_de_selo(img):
            return url

    # Depois tenta imagens CSS de fundo.
    for tag in elemento.select("[style]"):
        estilo = tag.get("style", "")
        match = re.search(r"background-image\s*:\s*url\(['\"]?(.*?)['\"]?\)", estilo, re.I)
        if match:
            url = url_imagem_valida(match.group(1), base)
            if url:
                return url

    # Algumas aplicações usam picture/source.
    for source in elemento.select("source"):
        url = extrair_srcset(
            source.get("data-srcset") or source.get("srcset"),
            base
        )
        if url:
            return url

    return ""


def imagem_de_selo(img):
    texto = normalizar(
        " ".join([
            str(img.get("alt", "")),
            str(img.get("title", "")),
            str(img.get("class", "")),
            str(img.get("src", "")),
        ])
    )
    return any(palavra in texto for palavra in (
        "selo", "zoneamento", "logo", "icone", "icon"
    ))


def nome_da_imagem(img):
    return normalizar(
        str(img.get("alt", "")) + " " + str(img.get("title", ""))
    )


def coletar_links_projetos(soup, base):
    links = {}

    for a in soup.select("a[href]"):
        href = urljoin(base, a.get("href", ""))
        caminho = urlparse(href).path.rstrip("/")

        # Páginas individuais da Econ usam /imovel/... singular.
        if not re.search(r"/imovel/[^/]+/[^/]+$", caminho):
            continue

        texto = normalizar(a.get_text(" ", strip=True))
        if texto:
            links.setdefault(caminho, href)

    return list(links.values())


def encontrar_cartao(tag):
    atual = tag

    for _ in range(7):
        if atual is None:
            break

        nome_tag = getattr(atual, "name", "")
        classes = " ".join(atual.get("class", []))
        identificacao = normalizar(classes + " " + str(atual.get("id", "")))

        if nome_tag in ("article", "li"):
            return atual

        if any(p in identificacao for p in (
            "card", "imovel", "imovel-item", "property",
            "empreendimento", "product"
        )):
            return atual

        atual = atual.parent

    return tag.parent or tag


def pontuacao_match(nome, texto):
    n = normalizar(nome)
    t = normalizar(texto)

    if not n or not t:
        return 0

    if n == t:
        return 100

    if n in t:
        return 80

    # Comparação por palavras para lidar com títulos com localização.
    palavras = [p for p in n.split() if len(p) > 2]
    if not palavras:
        return 0

    coincidencias = sum(1 for p in palavras if p in t)
    proporcao = coincidencias / len(palavras)

    if proporcao >= 0.8:
        return int(proporcao * 65)

    return 0


def extrair_catalogo(html, base):
    soup = BeautifulSoup(html, "html.parser")
    projetos = {}
    links = {}

    # Método principal: associa o nome do empreendimento à imagem do cartão.
    for titulo in soup.find_all(["h2", "h3", "h4"]):
        nome = titulo.get_text(" ", strip=True)
        nome_normalizado = normalizar(nome)

        if not nome_normalizado:
            continue

        cartao = encontrar_cartao(titulo)
        imagem = imagem_na_area(cartao, base)

        if imagem:
            projetos[nome_normalizado] = imagem
            print(f"[IMAGEM ENCONTRADA] {nome}: {imagem}")

        for a in cartao.select("a[href]"):
            href = urljoin(base, a.get("href", ""))
            caminho = urlparse(href).path.rstrip("/")
            if re.search(r"/imovel/[^/]+/[^/]+$", caminho):
                links[nome_normalizado] = href
                break

    # Método alternativo: usa o texto alternativo das imagens e seus cartões.
    for img in soup.select("img"):
        if imagem_de_selo(img):
            continue

        imagem = extrair_imagem_tag(img, base)
        if not imagem:
            continue

        alt = nome_da_imagem(img)
        if not alt:
            continue

        cartao = encontrar_cartao(img)
        texto_cartao = cartao.get_text(" ", strip=True) if cartao else ""
        descricao = alt + " " + normalizar(texto_cartao)

        chave = normalizar(alt)
        projetos.setdefault(chave, imagem)

        for titulo in cartao.select("h2, h3, h4") if cartao else []:
            nome = normalizar(titulo.get_text(" ", strip=True))
            if nome:
                projetos[nome] = imagem

    # Descobre links individuais para consultar imagens em páginas de projeto.
    for href in coletar_links_projetos(soup, base):
        caminho = urlparse(href).path.rstrip("/")
        slug = normalizar(caminho.split("/")[-1]).replace(" ", "-")
        links.setdefault(slug, href)

    return projetos, links


def escolher_imagem(nome, imagens):
    melhor = ""
    melhor_pontos = 0

    for descricao, url in imagens.items():
        pontos = pontuacao_match(nome, descricao)
        if pontos > melhor_pontos:
            melhor = url
            melhor_pontos = pontos

    if melhor_pontos >= 60:
        return melhor

    return ""


def extrair_imagem_pagina_projeto(url, nome):
    html = buscar_pagina(url)
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Prioriza imagens cujo alt/title mencione o nome do projeto.
    candidatas = []

    for img in soup.select("img"):
        if imagem_de_selo(img):
            continue

        imagem = extrair_imagem_tag(img, url)
        if not imagem:
            continue

        descricao = nome_da_imagem(img)
        pontos = pontuacao_match(nome, descricao)

        # Imagens grandes da galeria ou fachada são preferidas.
        largura = 0
        try:
            largura = int(img.get("width", 0))
        except (TypeError, ValueError):
            pass

        classe = normalizar(" ".join(img.get("class", [])))
        if any(p in classe for p in ("gallery", "banner", "hero", "fachada")):
            pontos += 10

        if pontos:
            candidatas.append((pontos, largura, imagem))

    if candidatas:
        candidatas.sort(reverse=True)
        return candidatas[0][2]

    # Fallback para Open Graph e Twitter Cards.
    for seletor, atributo in (
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
    ):
        tag = soup.select_one(seletor)
        if tag:
            imagem = url_imagem_valida(tag.get(atributo), url)
            if imagem:
                return imagem

    # Fallback: primeira imagem grande que não seja logo ou selo.
    for img in soup.select("img"):
        if imagem_de_selo(img):
            continue

        imagem = extrair_imagem_tag(img, url)
        if imagem:
            return imagem

    return ""


def carregar_dados_html(conteudo):
    inicio = conteudo.find(INICIO)
    fim = conteudo.find(FIM)

    if inicio < 0 or fim < 0 or fim <= inicio:
        raise RuntimeError(
            "Não encontrei os marcadores CATALOGO_DATA_INICIO/FIM no HTML."
        )

    bloco = conteudo[inicio + len(INICIO):fim]

    match = re.search(
        r"window\.EMPREENDIMENTOS\s*=\s*(\[[\s\S]*?\])\s*;",
        bloco
    )
    if not match:
        raise RuntimeError("Não encontrei window.EMPREENDIMENTOS no HTML.")

    dados = json.loads(match.group(1))
    return dados, match.group(1), inicio, fim


def atualizar_html(conteudo, dados, json_antigo, inicio, fim):
    novo_json = json.dumps(
        dados,
        ensure_ascii=False,
        indent=2
    )

    trecho = conteudo[inicio + len(INICIO):fim]
    novo_trecho, quantidade = re.subn(
        r"window\.EMPREENDIMENTOS\s*=\s*\[[\s\S]*?\]\s*;",
        "window.EMPREENDIMENTOS = " + novo_json + ";",
        trecho,
        count=1
    )

    if quantidade != 1:
        raise RuntimeError("Não consegui substituir o bloco do catálogo.")

    novo_conteudo = (
        conteudo[:inicio + len(INICIO)]
        + novo_trecho
        + conteudo[fim:]
    )

    return novo_conteudo


def main():
    if not ARQUIVO_HTML.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {ARQUIVO_HTML.resolve()}"
        )

    conteudo = ARQUIVO_HTML.read_text(encoding="utf-8")
    dados, json_antigo, inicio, fim = carregar_dados_html(conteudo)

    print(f"[INÍCIO] {len(dados)} empreendimentos no HTML.")

    # Consulta o catálogo oficial.
    html_catalogo = buscar_pagina(URL_CATALOGO)

    # Se a página principal falhar, tenta a página oficial alternativa.
    if not html_catalogo:
        html_catalogo = buscar_pagina(
            "https://econconstrutora.com.br/imoveis"
        )

    if not html_catalogo:
        raise RuntimeError(
            "Não foi possível acessar o catálogo oficial. "
            "Nenhuma alteração foi feita."
        )

    imagens, links = extrair_catalogo(html_catalogo, URL_CATALOGO)

    # Alguns sites entregam os dados de imagem na página inicial.
    if not imagens:
        html_home = buscar_pagina(DOMINIO_OFICIAL + "/")
        if html_home:
            imgs_home, links_home = extrair_catalogo(
                html_home, DOMINIO_OFICIAL + "/"
            )
            imagens.update(imgs_home)
            links.update(links_home)

    encontrados = 0
    pendentes = []

    for item in dados:
        nome = item.get("nome", "").strip()
        if not nome:
            continue

        # Preserva imagens existentes.
        imagem_atual = str(item.get("imagem", "") or "").strip()
        if imagem_atual:
            print(f"[MANTIDA] {nome}: já tem imagem.")
            continue

        imagem = escolher_imagem(nome, imagens)

        # Tenta encontrar o link individual a partir do slug.
        if not imagem:
            slug_procurado = normalizar(nome).replace(" ", "-")
            url_projeto = links.get(slug_procurado, "")

            if not url_projeto:
                for chave, href in links.items():
                    if pontuacao_match(nome, chave.replace("-", " ")) >= 60:
                        url_projeto = href
                        break

            # Se ainda não há link, tenta descobrir no catálogo pelo nome.
            if not url_projeto:
                soup = BeautifulSoup(html_catalogo, "html.parser")
                for titulo in soup.find_all(["h2", "h3", "h4"]):
                    if pontuacao_match(
                        nome, titulo.get_text(" ", strip=True)
                    ) >= 80:
                        cartao = encontrar_cartao(titulo)
                        link = cartao.select_one("a[href]") if cartao else None
                        if link:
                            url_projeto = urljoin(
                                URL_CATALOGO, link.get("href", "")
                            )
                            break

            if url_projeto:
                print(f"[CONSULTANDO PROJETO] {nome}: {url_projeto}")
                time.sleep(PAUSA)
                imagem = extrair_imagem_pagina_projeto(
                    url_projeto, nome
                )

        if imagem:
            item["imagem"] = imagem
            encontrados += 1
            print(f"[OK] {nome} => {imagem}")
        else:
            pendentes.append(nome)
            print(f"[SEM IMAGEM] {nome}")

    if encontrados:
        novo_conteudo = atualizar_html(
            conteudo, dados, json_antigo, inicio, fim
        )

        backup = ARQUIVO_HTML.with_suffix(".html.bak")
        backup.write_text(conteudo, encoding="utf-8")
        ARQUIVO_HTML.write_text(novo_conteudo, encoding="utf-8")

        print(f"[SALVO] {ARQUIVO_HTML}")
        print(f"[BACKUP] {backup}")
    else:
        print("[AVISO] Nenhuma imagem nova foi encontrada.")
        print("[AVISO] O HTML original foi mantido.")

    print()
    print("========== RESUMO ==========")
    print(f"Empreendimentos no catálogo: {len(dados)}")
    print(f"Imagens novas adicionadas: {encontrados}")
    print(f"Empreendimentos sem imagem: {len(pendentes)}")

    if pendentes:
        print("Lista sem imagem:")
        for nome in pendentes:
            print(f" - {nome}")

    if encontrados == 0:
        raise RuntimeError(
            "Nenhuma imagem nova foi encontrada. "
            "Veja os logs acima: o site pode ter alterado o HTML "
            "ou estar bloqueando requisições automatizadas."
        )


if __name__ == "__main__":
    main()

    except Exception as erro:
        print("\nERRO:", erro)
        print("O HTML original foi preservado.")
        sys.exit(1)
