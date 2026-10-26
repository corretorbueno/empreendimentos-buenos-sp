
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL_CATALOGO = "https://www.econconstrutora.com.br/imoveis"
ARQUIVO_JSON = Path("empreendimentos.json")
ARQUIVO_HTML = Path("empreendimentos.html")

# Imagens conhecidas dos empreendimentos Econ.
IMAGENS_CONHECIDAS = {
    "Volt Santana": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/volt-santana/perspectivas/perspectiva-da-fachada.webp",
    "Best Barra Funda": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/best-barra-funda/perspectivas/perspectiva-da-fachada.webp",
    "Tech Zona Sul": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/tech-zona-sul/perspectivas/perspectiva-da-fachada.webp",
    "Beat Jardim Botânico": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/beat-jardim-botanico/perspectivas/perspectiva-da-fachada.webp",
    "Free - Liberdade": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/free-liberdade/1771770373586.webp",
    "New Vila Ema": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/new-vila-ema/1773488349395.webp",
    "Vero Harmonia": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/thumbnails/vero-harmonia-thumb.webp",
    "Vero Encanto": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/vero-encanto/1771771925027.webp",
    "Like - Casa Verde": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/empreendimentos/like-casa-verde/1771770755949.webp",
    "Epic Jaguaré": "https://econ-portal-static.s3.sa-east-1.amazonaws.com/thumbnails/epic-jaguare-thumb.webp",
}


def limpar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def normalizar(texto):
    texto = (texto or "").casefold()
    texto = re.sub(r"[^a-z0-9]", "", texto)
    return texto


def imagem_valida(url):
    if not url:
        return ""

    url = urljoin(URL_CATALOGO, url.strip())

    if not url.startswith(("https://", "http://")):
        return ""

    if any(p in url.lower() for p in ("placeholder", "logo", "avatar")):
        return ""

    return url


def encontrar_imagem(bloco):
    atributos = (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
    )

    for img in bloco.find_all("img"):
        for atributo in atributos:
            url = imagem_valida(img.get(atributo, ""))
            if url:
                return url

        srcset = img.get("srcset", "")
        if srcset:
            primeira_url = srcset.split(",")[0].strip().split(" ")[0]
            url = imagem_valida(primeira_url)
            if url:
                return url

    return ""


def coletar_catalogo(soup):
    projetos = {}

    for titulo in soup.find_all(["h2", "h3", "h4"]):
        nome = limpar(titulo.get_text(" ", strip=True))

        if not nome or len(nome) > 100:
            continue

        bloco = titulo
        imagem = ""
        link = URL_CATALOGO

        for _ in range(7):
            if bloco.parent is None:
                break

            bloco = bloco.parent
            imagem = encontrar_imagem(bloco)

            ancora = bloco.find("a", href=True)
            if ancora:
                link = urljoin(URL_CATALOGO, ancora["href"])

            if imagem:
                break

        chave = normalizar(nome)

        projetos[chave] = {
            "nome": nome,
            "imagem": imagem,
            "link": link,
            "fonte": URL_CATALOGO,
        }

    return projetos


def atualizar_arquivos(projetos):
    # Aplica imagens conhecidas aos nomes correspondentes.
    por_nome = {
        normalizar(nome): url
        for nome, url in IMAGENS_CONHECIDAS.items()
    }

    lista_html = []

    for item in projetos.values():
        chave = normalizar(item["nome"])

        if not item["imagem"] and chave in por_nome:
            item["imagem"] = por_nome[chave]

        lista_html.append(item)

    documento = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "quantidade": len(lista_html),
        "com_imagem": sum(bool(p["imagem"]) for p in lista_html),
        "empreendimentos": lista_html,
    }

    ARQUIVO_JSON.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not ARQUIVO_HTML.exists():
        raise FileNotFoundError(
            "empreendimentos.html não foi encontrado na raiz do repositório."
        )

    html = ARQUIVO_HTML.read_text(encoding="utf-8")

    # Atualiza somente a lista existente entre os marcadores.
    padrao = re.compile(
        r"(<!-- CATALOGO_DATA_INICIO -->).*?"
        r"(<!-- CATALOGO_DATA_FIM -->)",
        re.DOTALL,
    )

    if not padrao.search(html):
        raise RuntimeError(
            "Os marcadores CATALOGO_DATA_INICIO e "
            "CATALOGO_DATA_FIM não foram encontrados no HTML."
        )

    dados = []

    # Preserva os projetos já cadastrados no site e suas informações.
    inicio = html.index("<!-- CATALOGO_DATA_INICIO -->")
    fim = html.index("<!-- CATALOGO_DATA_FIM -->")
    trecho = html[inicio:fim]

    correspondencias = re.search(
        r"window\.EMPREENDIMENTOS\s*=\s*(\[.*?\]);",
        trecho,
        re.DOTALL,
    )

    existentes = []

    if correspondencias:
        try:
            existentes = json.loads(correspondencias.group(1))
        except json.JSONDecodeError:
            existentes = []

    imagens_por_nome = {
        normalizar(p["nome"]): p["imagem"]
        for p in lista_html
        if p["imagem"]
    }

    for projeto in existentes:
        chave = normalizar(projeto.get("nome", ""))
        if not projeto.get("imagem") and chave in imagens_por_nome:
            projeto["imagem"] = imagens_por_nome[chave]
        dados.append(projeto)

    # Para projetos não encontrados no HTML, não cria cartões novos
    # automaticamente, evitando alterar a lista atual do usuário.

    novo_bloco = (
        "<!-- CATALOGO_DATA_INICIO -->\n"
        "<script>\n"
        "window.EMPREENDIMENTOS = "
        + json.dumps(dados, ensure_ascii=False, indent=2)
        + ";\n"
        "</script>\n"
        "<!-- CATALOGO_DATA_FIM -->"
    )

    html = padrao.sub(lambda _: novo_bloco, html, count=1)
    ARQUIVO_HTML.write_text(html, encoding="utf-8")

    print("Catálogo atualizado.")
    print(f"Empreendimentos encontrados no site Econ: {len(lista_html)}")
    print(f"Empreendimentos no HTML: {len(dados)}")
    print(
        "Imagens disponíveis no catálogo: "
        f"{sum(bool(p['imagem']) for p in lista_html)}"
    )


def main():
    print("Acessando o catálogo oficial da Econ...")

    resposta = requests.get(
        URL_CATALOGO,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=45,
    )
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")
    projetos = coletar_catalogo(soup)

    if not projetos:
        raise RuntimeError(
            "Nenhum empreendimento encontrado. "
            "O site pode carregar o catálogo por JavaScript."
        )

    atualizar_arquivos(projetos)


if __name__ == "__main__":
    main()
