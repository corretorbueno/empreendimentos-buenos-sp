
# -*- coding: utf-8 -*-
# atualizar_catalogo.py
# Preenche somente as imagens em empreendimentos.html.
# Instale antes: pip install requests beautifulsoup4

import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE = "https://www.econconstrutora.com.br"
PAGINAS = [
    BASE + "/imoveis",
    BASE + "/",
]
HTML = Path(__file__).resolve().parent / "empreendimentos.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()

def limpar(texto):
    return re.sub(r"\s+", " ", str(texto or "")).strip()

def encontrar_array(html):
    # Localiza o array existente sem exigir mudanças no HTML.
    padrao = re.compile(
        r"(window\s*\.\s*EMPREENDIMENTOS\s*=\s*)"
        r"(\[[\s\S]*?\])(\s*;?)"
    )
    m = padrao.search(html)
    if not m:
        raise RuntimeError(
            "Não encontrei window.EMPREENDIMENTOS no HTML. "
            "O arquivo original não será alterado."
        )
    try:
        dados = json.loads(m.group(2))
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "O array do catálogo não está em JSON válido. "
            "Nenhuma alteração foi feita."
        ) from e
    if not isinstance(dados, list):
        raise RuntimeError("O catálogo não é uma lista.")
    return m, dados

def url_imagem(img, pagina):
    # Testa os atributos comuns de imagens normais e lazy loading.
    for atributo in (
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
        "src",
    ):
        valor = limpar(img.get(atributo))
        if valor and not valor.startswith("data:"):
            url = urljoin(pagina, valor)
            if url.startswith(("https://", "http://")):
                return url

    # Imagens responsivas.
    for atributo in ("data-srcset", "srcset"):
        srcset = img.get(atributo, "")
        if srcset:
            opcoes = [
                parte.strip().split()[0]
                for parte in srcset.split(",")
                if parte.strip()
            ]
            for opcao in reversed(opcoes):
                if opcao.startswith("data:"):
                    continue
                url = urljoin(pagina, opcao)
                if url.startswith(("https://", "http://")):
                    return url
    return ""

def extrair_imagens():
    imagens = {}

    with requests.Session() as sessao:
        sessao.headers.update(HEADERS)

        for pagina in PAGINAS:
            print("Consultando:", pagina)

            try:
                resposta = sessao.get(pagina, timeout=30)
                resposta.raise_for_status()
            except requests.RequestException as erro:
                print("  Não foi possível acessar:", erro)
                continue

            soup = BeautifulSoup(resposta.text, "html.parser")

            # Cada imagem da página pode ter o nome no alt,
            # no título ou no texto do card que a contém.
            for img in soup.find_all("img"):
                url = url_imagem(img, resposta.url)
                if not url:
                    continue

                alt = limpar(img.get("alt"))
                titulo = limpar(img.get("title"))
                candidatos = [alt, titulo]

                # Sobe na árvore para identificar o card correspondente.
                pai = img
                for _ in range(5):
                    if pai.parent is None:
                        break
                    pai = pai.parent
                    if getattr(pai, "name", "") in (
                        "article", "li", "section"
                    ):
                        break

                texto_card = limpar(pai.get_text(" ", strip=True))
                candidatos.append(texto_card)

                # O alt frequentemente contém, por exemplo,
                # "Volt Santana - Apartamento ...".
                for candidato in candidatos:
                    chave = normalizar(candidato)
                    if not chave:
                        continue

                    # Guarda texto para correspondência posterior.
                    # Imagens genéricas de selos são descartadas.
                    if any(
                        termo in chave
                        for termo in (
                            "selo de zoneamento",
                            "simulacao de financiamento",
                            "logo econ",
                        )
                    ):
                        continue

                    imagens.setdefault(chave, url)

    if not imagens:
        raise RuntimeError(
            "Nenhuma imagem foi extraída das páginas. "
            "O site pode exigir JavaScript para exibir as imagens. "
            "O HTML não foi alterado."
        )

    print(f"Referências de imagens encontradas: {len(imagens)}")
    return imagens

def melhor_imagem(nome, imagens):
    alvo = normalizar(nome)
    if not alvo:
        return ""

    # Primeiro procura correspondência exata do nome.
    if alvo in imagens:
        return imagens[alvo]

    # Depois procura o nome dentro do alt/texto do card.
    # Só aceita se todos os termos significativos do nome aparecerem.
    termos = alvo.split()
    candidatos = []

    for descricao, url in imagens.items():
        if alvo and alvo in descricao:
            candidatos.append((len(descricao), url))
            continue

        if len(termos) >= 2 and all(t in descricao for t in termos):
            candidatos.append((len(descricao), url))

    # A descrição mais curta costuma ser o alt específico da imagem,
    # em vez do texto inteiro da página.
    if candidatos:
        candidatos.sort(key=lambda x: x[0])
        return candidatos[0][1]

    return ""

def main():
    print("=" * 55)
    print("ATUALIZADOR DE IMAGENS — ECON CONSTRUTORA")
    print("=" * 55)

    if not HTML.exists():
        raise RuntimeError(
            f"Arquivo não encontrado: {HTML}\n"
            "Coloque este script na pasta onde está empreendimentos.html."
        )

    html_original = HTML.read_text(encoding="utf-8")
    match, empreendimentos = encontrar_array(html_original)

    print("Empreendimentos no HTML:", len(empreendimentos))

    imagens = extrair_imagens()

    alterados = 0
    ja_preenchidos = 0
    sem_imagem = []

    for item in empreendimentos:
        if not isinstance(item, dict):
            continue

        nome = (
            item.get("nome")
            or item.get("titulo")
            or item.get("empreendimento")
            or ""
        )

        if not limpar(nome):
            continue

        # Não substitui imagem que já existe.
        imagem_atual = limpar(item.get("imagem"))
        if imagem_atual:
            ja_preenchidos += 1
            continue

        imagem = melhor_imagem(nome, imagens)

        if imagem:
            item["imagem"] = imagem
            alterados += 1
            print(f"[OK] {nome}")
            print(f"     {imagem}")
        else:
            sem_imagem.append(nome)
            print(f"[SEM IMAGEM] {nome}")

    if alterados == 0:
        print("\nNenhuma imagem nova foi associada.")
        print("O HTML original foi preservado.")
        print(
            "Isso indica que as imagens não foram encontradas "
            "ou os nomes não corresponderam."
        )
        if sem_imagem:
            print("\nEmpreendimentos sem imagem:")
            for nome in sem_imagem:
                print(" -", nome)
        return

    array_novo = json.dumps(
        empreendimentos,
        ensure_ascii=False,
        indent=2,
    )

    html_novo = (
        html_original[:match.start(2)]
        + array_novo
        + html_original[match.end(2):]
    )

    # Backup do HTML antes de gravar.
    horario = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = HTML.with_name(
        f"{HTML.stem}_{horario}.backup.html"
    )
    backup.write_text(html_original, encoding="utf-8")

    temporario = HTML.with_name(HTML.name + ".tmp")
    temporario.write_text(html_novo, encoding="utf-8")
    temporario.replace(HTML)

    print("\n" + "=" * 55)
    print("ATUALIZAÇÃO CONCLUÍDA")
    print("Imagens preenchidas:", alterados)
    print("Imagens que já existiam:", ja_preenchidos)
    print("Empreendimentos sem imagem:", len(sem_imagem))
    print("Backup:", backup.name)
    print("=" * 55)

    if sem_imagem:
        print("\nAinda sem imagem:")
        for nome in sem_imagem:
            print(" -", nome)

if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print("\nERRO:", erro)
        print("O HTML original foi preservado.")
        sys.exit(1)
