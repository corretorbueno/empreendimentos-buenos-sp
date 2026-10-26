
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SITE = "https://www.econconstrutora.com.br/imoveis"
ARQUIVO = Path("empreendimentos.json")
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def limpar(valor):
    return re.sub(r"\s+", " ", valor or "").strip()


def url_absoluta(valor, pagina=SITE):
    if not valor:
        return ""

    valor = valor.strip()

    if valor.startswith(("data:", "javascript:")):
        return ""

    return urljoin(pagina, valor)


def imagem_do(elemento):
    """Retorna uma imagem encontrada no card do projeto."""
    for img in elemento.select("img"):
        alt = limpar(img.get("alt", "")).lower()
        caminho = " ".join([
            str(img.get("src", "")),
            str(img.get("class", "")),
            alt,
        ]).lower()

        if "selo de zoneamento" in alt:
            continue

        if "logo" in caminho or "icone" in caminho or "ícone" in caminho:
            continue

        candidatos = [
            img.get("src"),
            img.get("data-src"),
            img.get("data-lazy-src"),
            img.get("data-original"),
            img.get("data-image"),
        ]

        for atributo in ("srcset", "data-srcset"):
            srcset = img.get(atributo, "")
            if srcset:
                primeiro = srcset.split(",")[0].strip().split()
                if primeiro:
                    candidatos.append(primeiro[0])

        for candidato in candidatos:
            url = url_absoluta(candidato)
            if not url:
                continue

            caminho_url = urlparse(url).path.lower()

            if caminho_url.endswith((".svg", ".ico")):
                continue

            if "selo" in caminho_url or "logo" in caminho_url:
                continue

            return url

    # Algumas páginas usam background-image.
    for elemento_css in elemento.select("[style]"):
        estilo = elemento_css.get("style", "")
        encontrado = re.search(
            r"background(?:-image)?\s*:[^;]*url\(['\"]?(.*?)['\"]?\)",
            estilo,
            re.I,
        )

        if encontrado:
            url = url_absoluta(encontrado.group(1))
            if url:
                return url

    return ""


def identificar_status(texto):
    texto = texto.lower()

    opcoes = [
        ("futuro lançamento", "Futuro Lançamento"),
        ("breve lançamento", "Breve Lançamento"),
        ("lançamento", "Lançamento"),
        ("em construção", "Em Construção"),
        ("pronto para morar", "Pronto para Morar"),
    ]

    for chave, nome in opcoes:
        if chave in texto:
            return nome

    return ""


def identificar_dormitorios(texto):
    encontrado = re.search(
        r"\b\d+(?:\s*e\s*\d+)?\s*dorms?\.?",
        texto,
        re.I,
    )
    return limpar(encontrado.group(0)) if encontrado else ""


def encontrar_card(titulo):
    """
    Sobe pela árvore HTML procurando um contêiner compacto
    com o título e uma imagem. Evita usar a página inteira.
    """
    melhor = titulo

    atual = titulo
    for _ in range(8):
        pai = atual.parent

        if pai is None:
            break

        atual = pai
        texto = limpar(atual.get_text(" ", strip=True))

        if len(texto) > 1600:
            break

        if atual.find("img"):
            melhor = atual

            if len(texto) < 650:
                break

    return melhor


def coletar():
    resposta = requests.get(
        SITE,
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")
    projetos = {}

    for titulo in soup.find_all(["h2", "h3", "h4"]):
        nome = limpar(titulo.get_text(" ", strip=True))

        if not nome or len(nome) > 100:
            continue

        card = encontrar_card(titulo)
        texto_card = limpar(card.get_text(" ", strip=True))
        imagem = imagem_do(card)

        link = ""
        for ancora in card.find_all("a", href=True):
            candidato = url_absoluta(ancora["href"])
            caminho = urlparse(candidato).path

            if "/detalhes/" in caminho:
                link = candidato
                break

        # Se o card não expôs a imagem, tenta os pais mais próximos.
        if not imagem:
            atual = titulo
            for _ in range(5):
                if atual.parent is None:
                    break
                atual = atual.parent
                imagem = imagem_do(atual)
                if imagem:
                    break

        # Não incluir títulos genéricos da navegação.
        nome_normalizado = nome.lower()
        ignorar = {
            "imóveis", "empreendimentos", "destaques",
            "ver todos", "buscar empreendimento ou região",
        }

        if nome_normalizado in ignorar:
            continue

        projeto = {
            "nome": nome,
            "imagem": imagem,
            "link": link or SITE,
            "status": identificar_status(texto_card),
            "localizacao": "",
            "dormitorios": identificar_dormitorios(texto_card),
            "descricao": texto_card[:500],
            "fonte": SITE,
        }

        # A localização costuma aparecer como "Zona Norte|Santana".
        local = re.search(
            r"(Zona\s+(?:Norte|Sul|Leste|Oeste)|Centro|"
            r"Santo André|Guarulhos|Diadema|Osasco|Mauá)"
            r"\s*\|\s*([^|]{2,80})",
            texto_card,
            re.I,
        )

        if local:
            projeto["localizacao"] = limpar(local.group(0))

        # Mantém uma única entrada por nome.
        chave = nome.casefold()
        existente = projetos.get(chave)

        if existente is None:
            projetos[chave] = projeto
        elif not existente["imagem"] and projeto["imagem"]:
            projetos[chave] = projeto

    resultado = sorted(
        projetos.values(),
        key=lambda p: p["nome"].casefold(),
    )

    # Não sobrescreve o JSON publicado se a página mudar ou a coleta falhar.
    if len(resultado) < 5:
        raise RuntimeError(
            f"A coleta encontrou apenas {len(resultado)} projetos. "
            "O arquivo anterior será preservado. "
            "Verifique a estrutura atual do site da Econ."
        )

    com_imagem = sum(bool(p["imagem"]) for p in resultado)

    dados = {
        "origem": SITE,
        "atualizado_em": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "quantidade": len(resultado),
        "com_imagem": com_imagem,
        "empreendimentos": resultado,
    }

    # Escreve primeiro em arquivo temporário e só depois substitui o JSON.
    temporario = ARQUIVO.with_suffix(".tmp")

    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(ARQUIVO)

    print("Catálogo atualizado.")
    print("Total de empreendimentos:", len(resultado))
    print("Com imagem:", com_imagem)
    print("Sem imagem:", len(resultado) - com_imagem)
    print("JSON salvo em:", ARQUIVO)


if __name__ == "__main__":
    coletar()

