
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SITE = "https://www.econconstrutora.com.br/imoveis"
RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_SAIDA = RAIZ / "empreendimentos.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

def texto_limpo(texto):
    return re.sub(r"\s+", " ", texto or "").strip()

def url_imagem(img, pagina):
    """Retorna uma URL de imagem encontrada no HTML da Econ."""
    if img is None:
        return ""

    atributos = [
        img.get("src"),
        img.get("data-src"),
        img.get("data-lazy-src"),
        img.get("data-original"),
        img.get("data-image"),
    ]

    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        candidatos = [
            parte.strip().split(" ")[0]
            for parte in srcset.split(",")
            if parte.strip()
        ]
        atributos.extend(candidatos)

    for valor in atributos:
        if not valor:
            continue

        valor = valor.strip()
        if valor.startswith("data:"):
            continue

        resultado = urljoin(pagina, valor)
        if resultado.startswith(("https://", "http://")):
            return resultado

    return ""

def extrair_catalogo():
    print(f"Acessando catálogo: {SITE}")

    resposta = requests.get(
        SITE,
        headers=HEADERS,
        timeout=35,
    )
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")
    projetos = []
    vistos = set()

    # Procura links de projetos e tenta localizar imagem e título.
    for link in soup.select("a[href]"):
        href = link.get("href", "").strip()
        if not href:
            continue

        href_completo = urljoin(SITE, href)
        texto_link = texto_limpo(link.get_text(" ", strip=True))

        imagem_tag = link.find("img")
        alt = texto_limpo(imagem_tag.get("alt", "")) if imagem_tag else ""

        titulo = texto_link or alt
        if not titulo:
            continue

        # Ignora navegação, redes sociais e links que não parecem projetos.
        if not any(palavra in href_completo.lower() for palavra in (
            "/imoveis", "/imovel", "/empreendimento", "/detalhe", "/produto"
        )):
            continue

        if href_completo.rstrip("/") == SITE.rstrip("/"):
            continue

        chave = href_completo.split("#")[0].rstrip("/")
        if chave in vistos:
            continue

        # Escolhe o menor bloco próximo do link para obter contexto.
        bloco = link
        for _ in range(4):
            if bloco.parent and bloco.parent.name not in ("body", "html"):
                bloco = bloco.parent

        if len(titulo) > 110:
            titulo = alt or texto_link

        if not titulo or len(titulo) > 110:
            continue

        foto = url_imagem(imagem_tag, SITE) if imagem_tag else ""

        # Se não houver imagem no link, tenta encontrar uma no mesmo bloco.
        if not foto:
            outra_img = bloco.find("img")
            foto = url_imagem(outra_img, SITE) if outra_img else ""

        texto_bloco = texto_limpo(bloco.get_text(" ", strip=True))

        projetos.append({
            "nome": titulo,
            "titulo": titulo,
            "local": "",
            "regiao": "",
            "bairro": "",
            "dormitorios": "",
            "status": "",
            "imagem": foto,
            "image": foto,
            "url": href_completo,
            "descricao": texto_bloco[:500],
        })
        vistos.add(chave)

    if len(projetos) < 5:
        raise RuntimeError(
            "Foram encontrados menos de 5 projetos. "
            "O site pode ter alterado o HTML ou carregado os dados via JavaScript. "
            "O JSON anterior será preservado."
        )

    return projetos

def main():
    try:
        projetos = extrair_catalogo()
    except Exception as erro:
        print(f"ERRO ao consultar o catálogo: {erro}", file=sys.stderr)
        sys.exit(1)

    dados = {
        "origem": SITE,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "quantidade": len(projetos),
        "com_imagem": sum(bool(p["imagem"]) for p in projetos),
        "empreendimentos": projetos,
    }

    temporario = ARQUIVO_SAIDA.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(ARQUIVO_SAIDA)

    print(f"Projetos encontrados: {len(projetos)}")
    print(f"Projetos com imagem: {dados['com_imagem']}")
    print(f"Arquivo salvo: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    main()
