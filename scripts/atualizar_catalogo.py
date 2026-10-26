
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urldefrag

import requests
from bs4 import BeautifulSoup

URL_BASE = "https://www.econconstrutora.com.br"
ARQUIVO_SAIDA = Path("empreendimentos.json")

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
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    ).casefold().strip()


def buscar_pagina(url):
    resposta = SESSAO.get(url, timeout=40)
    resposta.raise_for_status()
    return BeautifulSoup(resposta.text, "html.parser")


def obter_imagem(bloco):
    for imagem in bloco.find_all("img"):
        for atributo in (
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
        ):
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

    # Identifica links que parecem levar à página individual
    # de um empreendimento, sem depender apenas dos títulos.
    for ancora in soup.find_all("a", href=True):
        href = urljoin(url_pagina, ancora["href"])
        href, _ = urldefrag(href)

        if not href.startswith(URL_BASE):
            continue

        texto_link = texto_limpo(ancora.get_text(" ", strip=True))

        # Procura um título dentro do link ou de seu card.
        bloco = ancora
        for _ in range(5):
            if bloco.parent is None:
                break
            bloco = bloco.parent

            texto_bloco = texto_limpo(
                bloco.get_text(" ", strip=True)
            )

            if (
                bloco.find(["h2", "h3", "h4"])
                and len(texto_bloco) <= 1800
            ):
                break

        titulo = (
            ancora.find(["h2", "h3", "h4"])
            or bloco.find(["h2", "h3", "h4"])
        )

        nome = texto_limpo(
            titulo.get_text(" ", strip=True)
            if titulo
            else texto_link
        )

        if not nome or len(nome) > 100:
            continue

        if len(nome.split()) > 12:
            continue

        nome_normalizado = normalizar(nome)

        # Descarta links genéricos de navegação e chamadas de ação.
        termos_invalidos = (
            "saiba mais",
            "ver mais",
            "ver todos",
            "conheca",
            "conheça",
            "fale conosco",
            "comprar",
            "financiamento",
            "menu",
            "buscar",
            "pesquisar",
        )

        if any(termo in nome_normalizado for termo in termos_invalidos):
            continue

        # Mantém apenas links internos que aparentam ser imóveis.
        caminho = href.removeprefix(URL_BASE).strip("/")
        if not caminho or caminho == "imoveis":
            continue

        if caminho.startswith(("blog", "noticias", "contato", "sobre")):
            continue

        imagem = obter_imagem(bloco)

        texto_card = texto_limpo(bloco.get_text(" ", strip=True))

        projetos[nome_normalizado] = {
            "nome": nome,
            "imagem": imagem,
            "link": href,
            "fonte": url_pagina,
            "descricao": texto_card[:500],
        }

    return projetos


def main():
    print("Consultando o catálogo público da Econ...")

    projetos = {}
    erros = []

    for url in PAGINAS_CATALOGO:
        try:
            print(f"\nAcessando: {url}")
            soup = buscar_pagina(url)
            encontrados = encontrar_projetos(soup, url)

            novos = 0
            for chave, projeto in encontrados.items():
                if chave not in projetos:
                    projetos[chave] = projeto
                    novos += 1
                elif (
                    not projetos[chave]["imagem"]
                    and projeto["imagem"]
                ):
                    projetos[chave]["imagem"] = projeto["imagem"]

            print(
                f"Encontrados nesta página: {len(encontrados)} "
                f"| Novos: {novos}"
            )

        except requests.RequestException as erro:
            mensagem = f"{url}: {erro}"
            erros.append(mensagem)
            print(f"AVISO: não foi possível consultar {mensagem}")

        time.sleep(1)

    lista = list(projetos.values())

    # Não sobrescreve o catálogo existente com uma coleta claramente
    # incompleta ou vazia.
    if len(lista) < 10:
        detalhes = "\n".join(erros)
        raise RuntimeError(
            f"Foram encontrados apenas {len(lista)} empreendimentos. "
            "O arquivo de saída não será substituído. "
            "Pode ser necessário adaptar a coleta ao HTML atual da Econ."
            + (f"\nFalhas de acesso:\n{detalhes}" if detalhes else "")
        )

    lista.sort(key=lambda item: normalizar(item["nome"]))

    documento = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "quantidade": len(lista),
        "empreendimentos": lista,
    }

    ARQUIVO_SAIDA.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    com_imagem = sum(
        1 for projeto in lista if projeto["imagem"]
    )

    print("\nAtualização concluída.")
    print(f"Empreendimentos únicos encontrados: {len(lista)}")
    print(f"Com imagem: {com_imagem}")
    print(f"Sem imagem: {len(lista) - com_imagem}")
    print(f"Arquivo gerado: {ARQUIVO_SAIDA}")

    if erros:
        print(
            f"Atenção: {len(erros)} página(s) não puderam ser consultadas."
        )


if __name__ == "__main__":
    main()
