
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SITE = "https://www.econconstrutora.com.br/imoveis"
ARQUIVO = Path("empreendimentos.json")
TIMEOUT = 30

CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def limpar(valor):
    return re.sub(r"\s+", " ", valor or "").strip()


def normalizar(valor):
    valor = unicodedata.normalize("NFKD", valor or "")
    return "".join(
        caractere for caractere in valor
        if not unicodedata.combining(caractere)
    ).casefold().strip()


def url_absoluta(valor, pagina=SITE):
    if not valor:
        return ""

    valor = valor.strip()

    if valor.startswith(("data:", "javascript:")):
        return ""

    return urljoin(pagina, valor)


def obter_imagem(elemento):
    """Busca a imagem principal dentro do card do empreendimento."""
    for img in elemento.select("img"):
        alt = limpar(img.get("alt", ""))

        if "selo de zoneamento" in normalizar(alt):
            continue

        candidatos = [
            img.get("src"),
            img.get("data-src"),
            img.get("data-lazy-src"),
            img.get("data-original"),
            img.get("data-image"),
        ]

        srcset = img.get("srcset") or img.get("data-srcset")

        if srcset:
            primeiro = srcset.split(",")[0].strip().split()
            if primeiro:
                candidatos.append(primeiro[0])

        for candidato in candidatos:
            url = url_absoluta(candidato)

            if not url:
                continue

            caminho = urlparse(url).path.lower()

            if caminho.endswith((".svg", ".ico")):
                continue

            if "logo" in caminho or "selo" in caminho:
                continue

            return url

    # Algumas páginas usam imagens de fundo em CSS.
    for item in elemento.select("[style]"):
        estilo = item.get("style", "")
        achado = re.search(
            r"background(?:-image)?\s*:[^;]*url\(['\"]?(.*?)['\"]?\)",
            estilo,
            re.I,
        )

        if achado:
            url = url_absoluta(achado.group(1))
            if url:
                return url

    return ""


def status_do(texto):
    texto = normalizar(texto)

    opcoes = [
        ("futuro lancamento", "Futuro Lançamento"),
        ("breve lancamento", "Breve Lançamento"),
        ("lancamento", "Lançamento"),
        ("em construcao", "Em Construção"),
        ("pronto para morar", "Pronto para Morar"),
    ]

    for chave, resultado in opcoes:
        if chave in texto:
            return resultado

    return ""


def extrair_localizacao(texto):
    padrao = re.search(
        r"(Zona\s+(?:Leste|Sul|Norte|Oeste)|Centro|Santo André|"
        r"Guarulhos|Diadema|Osasco|São Bernardo do Campo|"
        r"São Caetano do Sul|Mauá|Suzano|Mogi das Cruzes)"
        r"\s*\|\s*([^|]{2,70})",
        texto,
        re.I,
    )

    if padrao:
        return limpar(padrao.group(0))

    return ""


def extrair_projetos():
    resposta = requests.get(
        SITE,
        headers=CABECALHOS,
        timeout=TIMEOUT,
    )
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")
    encontrados = {}

    for titulo in soup.find_all(["h2", "h3", "h4"]):
        nome = limpar(titulo.get_text(" ", strip=True))

        if not nome or len(nome) > 100:
            continue

        # Procura um contêiner próximo que tenha a foto e o link do projeto.
        contenedor = titulo
        melhor = titulo

        for _ in range(7):
            pai = contenedor.parent

            if pai is None:
                break

            contenedor = pai
            texto = limpar(contenedor.get_text(" ", strip=True))

            if len(texto) > 1800:
                break

            if contenedor.find("img"):
                melhor = contenedor

                if len(texto) < 700:
                    break

        texto_card = limpar(melhor.get_text(" ", strip=True))
        imagem = obter_imagem(melhor)
        link = ""

        # Prioriza um link específico de detalhes do empreendimento.
        for ancora in melhor.find_all("a", href=True):
            candidato = url_absoluta(ancora["href"])

            if "/detalhes/" in urlparse(candidato).path:
                link = candidato
                break

        if not link:
            ancora = titulo.find_parent("a", href=True)

            if ancora:
                candidato = url_absoluta(ancora["href"])

                if "/detalhes/" in urlparse(candidato).path:
                    link = candidato

        # Se a imagem não estiver no contêiner imediato, tenta os ancestrais.
        if not imagem:
            pai = titulo

            for _ in range(5):
                if pai.parent is None:
                    break

                pai = pai.parent
                imagem = obter_imagem(pai)

                if imagem:
                    break

        dormitorios = ""
        achado_dorm = re.search(
            r"\b\d+(?:\s*e\s*\d+)?\s*dorms?\.?",
            texto_card,
            re.I,
        )

        if achado_dorm:
            dormitorios = limpar(achado_dorm.group(0))

        projeto = {
            "nome": nome,
            "imagem": imagem,
            "link": link or SITE,
            "status": status_do(texto_card),
            "localizacao": extrair_localizacao(texto_card),
            "dormitorios": dormitorios,
            "descricao": texto_card[:500],
            "fonte": SITE,
        }

        chave = normalizar(nome)

        # Mantém a melhor versão se o mesmo projeto aparecer mais de uma vez.
        atual = encontrados.get(chave)

        if atual is None or (
            not atual["imagem"] and projeto["imagem"]
        ):
            encontrados[chave] = projeto

    projetos = sorted(
        encontrados.values(),
        key=lambda projeto: normalizar(projeto["nome"]),
    )

    if len(projetos) < 5:
        raise RuntimeError(
            f"A Econ retornou apenas {len(projetos)} projetos. "
            "O catálogo anterior será preservado. "
            "Pode ser necessário ajustar a extração ao HTML atual do site."
        )

    com_imagem = sum(bool(p["imagem"]) for p in projetos)

    dados = {
        "origem": SITE,
        "atualizado_em": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "quantidade": len(projetos),
        "com_imagem": com_imagem,
        "empreendimentos": projetos,
    }

    temporario = ARQUIVO.with_suffix(".json.tmp")

    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Substitui o JSON apenas depois de terminar a coleta e validação.
    temporario.replace(ARQUIVO)

    print("Catálogo atualizado.")
    print("Total de empreendimentos:", len(projetos))
    print("Com imagem:", com_imagem)
    print("Sem imagem:", len(projetos) - com_imagem)
    print("Arquivo:", ARQUIVO)


if __name__ == "__main__":
    extrair_projetos()

