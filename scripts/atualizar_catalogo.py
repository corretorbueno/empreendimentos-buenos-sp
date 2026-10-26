
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL_CATALOGO = "https://www.econconstrutora.com.br/imoveis"
ARQUIVO_SAIDA = Path("empreendimentos.json")


def texto_limpo(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def main():
    print("Acessando o catalogo publico da Econ...")

    resposta = requests.get(
        URL_CATALOGO,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")
    projetos = {}

    for titulo in soup.find_all(["h2", "h3", "h4"]):
        nome = texto_limpo(titulo.get_text(" ", strip=True))

        if not nome or len(nome) > 100:
            continue

        bloco = titulo

        for _ in range(6):
            if bloco.parent is None:
                break

            bloco = bloco.parent

            if bloco.find("img"):
                break

        imagem = ""

        for img in bloco.find_all("img"):
            imagem = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or ""
            )

            if imagem:
                break

        ancora = titulo.find_parent("a")

        if not ancora:
            ancora = bloco.find("a", href=True)

        link = urljoin(
            URL_CATALOGO,
            ancora["href"] if ancora and ancora.get("href") else ""
        )

        projetos[nome.casefold()] = {
            "nome": nome,
            "imagem": urljoin(URL_CATALOGO, imagem) if imagem else "",
            "link": link,
            "fonte": URL_CATALOGO,
        }

    lista = list(projetos.values())

    if not lista:
        raise RuntimeError(
            "Nenhum empreendimento encontrado. "
            "Precisamos verificar como o catalogo carrega os dados."
        )

    documento = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "quantidade": len(lista),
        "empreendimentos": lista,
    }

    ARQUIVO_SAIDA.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    com_imagem = sum(1 for item in lista if item["imagem"])

    print(f"Empreendimentos encontrados: {len(lista)}")
    print(f"Com imagem: {com_imagem}")
    print(f"Sem imagem: {len(lista) - com_imagem}")
    print(f"Arquivo gerado: {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
