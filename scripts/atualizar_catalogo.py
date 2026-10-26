
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Atualiza as imagens do catálogo da Econ dentro de empreendimentos.html.

- Preserva o layout e os demais scripts do HTML.
- Preserva os empreendimentos já cadastrados.
- Preenche imagens conhecidas sem sobrescrever imagens existentes.
- Cria backup antes de salvar alterações.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# CONFIGURAÇÃO
# ============================================================

PASTA = Path(__file__).resolve().parent
ARQUIVO_HTML = PASTA / "empreendimentos.html"

MARCADOR_INICIO = "<!-- CATALOGO_DATA_INICIO -->"
MARCADOR_FIM = "<!-- CATALOGO_DATA_FIM -->"

CRIAR_BACKUP = True


# Imagens conhecidas dos empreendimentos Econ.
# Novas URLs só devem ser adicionadas quando forem confirmadas.
IMAGENS_ECON = {
    "volt santana": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/volt-santana/perspectivas/"
        "perspectiva-da-fachada.webp"
    ),
    "best barra funda": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/best-barra-funda/perspectivas/"
        "perspectiva-da-fachada.webp"
    ),
    "tech zona sul": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/tech-zona-sul/perspectivas/"
        "perspectiva-da-fachada.webp"
    ),
    "beat jardim botanico": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/beat-jardim-botanico/perspectivas/"
        "perspectiva-da-fachada.webp"
    ),
    "free liberdade": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/free-liberdade/1771770373586.webp"
    ),
    "new vila ema": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/new-vila-ema/1773488349395.webp"
    ),
    "vero harmonia": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "thumbnails/vero-harmonia-thumb.webp"
    ),
    "vero encanto": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/vero-encanto/1771771925027.webp"
    ),
    "like casa verde": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "empreendimentos/like-casa-verde/1771770755949.webp"
    ),
    "epic jaguare": (
        "https://econ-portal-static.s3.sa-east-1.amazonaws.com/"
        "thumbnails/epic-jaguare-thumb.webp"
    ),
}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar(texto: Any) -> str:
    """Normaliza nomes para facilitar a comparação."""
    import unicodedata

    valor = str(texto or "").strip().lower()
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(
        caractere
        for caractere in valor
        if not unicodedata.combining(caractere)
    )
    valor = re.sub(r"[^a-z0-9]+", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def validar_url_imagem(url: Any) -> bool:
    """Aceita apenas URLs HTTPS para imagens."""
    if not isinstance(url, str):
        return False

    url = url.strip()

    return (
        url.startswith("https://")
        and " " not in url
        and len(url) < 2000
    )


def localizar_catalogo(html: str) -> tuple[int, int, str]:
    """
    Localiza o array window.EMPREENDIMENTOS entre os marcadores.
    Retorna início, fim e conteúdo do array.
    """
    inicio_marcador = html.find(MARCADOR_INICIO)
    fim_marcador = html.find(MARCADOR_FIM)

    if inicio_marcador == -1 or fim_marcador == -1:
        raise ValueError(
            "Não encontrei os marcadores do catálogo no HTML. "
            "Confira CATALOGO_DATA_INICIO e CATALOGO_DATA_FIM."
        )

    if fim_marcador <= inicio_marcador:
        raise ValueError("Os marcadores do catálogo estão fora de ordem.")

    trecho = html[inicio_marcador + len(MARCADOR_INICIO):fim_marcador]

    correspondencia = re.search(
        r"window\s*\.\s*EMPREENDIMENTOS\s*=\s*(\[.*?\])\s*;",
        trecho,
        flags=re.DOTALL,
    )

    if not correspondencia:
        raise ValueError(
            "Não encontrei window.EMPREENDIMENTOS = [...] "
            "entre os marcadores."
        )

    return (
        inicio_marcador,
        fim_marcador,
        correspondencia.group(1),
    )


def carregar_catalogo(texto_array: str) -> list[dict[str, Any]]:
    """Lê o array de empreendimentos como JSON válido."""
    try:
        dados = json.loads(texto_array)
    except json.JSONDecodeError as erro:
        raise ValueError(
            "O catálogo não está em formato JSON válido. "
            "Confira aspas, vírgulas e chaves do array."
        ) from erro

    if not isinstance(dados, list):
        raise ValueError("O catálogo precisa ser uma lista.")

    if not dados:
        raise ValueError("O catálogo está vazio. Nada foi alterado.")

    if not all(isinstance(item, dict) for item in dados):
        raise ValueError(
            "Todos os empreendimentos precisam ser objetos JSON."
        )

    return dados


def encontrar_imagem(nome: str) -> str | None:
    """Retorna a imagem conhecida para um nome normalizado."""
    nome_normalizado = normalizar(nome)

    for nome_cadastrado, url in IMAGENS_ECON.items():
        if normalizar(nome_cadastrado) == nome_normalizado:
            return url

    return None


def atualizar_imagens(
    empreendimentos: list[dict[str, Any]]
) -> tuple[int, int]:
    """
    Preenche somente imagens vazias.
    Não substitui uma imagem já cadastrada.
    """
    adicionadas = 0
    mantidas = 0

    for item in empreendimentos:
        nome = item.get("nome") or item.get("titulo") or ""

        if not nome:
            print("AVISO: empreendimento sem nome; ignorado.")
            continue

        imagem_atual = str(item.get("imagem") or "").strip()

        if imagem_atual:
            mantidas += 1
            continue

        nova_imagem = encontrar_imagem(nome)

        if nova_imagem and validar_url_imagem(nova_imagem):
            item["imagem"] = nova_imagem
            adicionadas += 1
            print(f"Imagem adicionada: {nome}")
        else:
            # Não inventa URLs para projetos sem imagem confirmada.
            item["imagem"] = imagem_atual

    return adicionadas, mantidas


def gerar_backup(caminho: Path) -> Path:
    """Cria uma cópia do HTML original."""
    horario = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = caminho.with_name(
        f"{caminho.stem}.backup_{horario}{caminho.suffix}"
    )
    backup.write_bytes(caminho.read_bytes())
    return backup


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main() -> int:
    print("=" * 58)
    print("ATUALIZADOR DO CATÁLOGO ECON")
    print("=" * 58)

    if not ARQUIVO_HTML.exists():
        print(f"ERRO: arquivo não encontrado: {ARQUIVO_HTML}")
        return 1

    try:
        html_original = ARQUIVO_HTML.read_text(encoding="utf-8")

        inicio_marcador, fim_marcador, array_original = (
            localizar_catalogo(html_original)
        )

        empreendimentos = carregar_catalogo(array_original)

        print(f"Empreendimentos encontrados: {len(empreendimentos)}")

        # Validação antes de modificar qualquer arquivo.
        nomes = [
            normalizar(
                item.get("nome") or item.get("titulo") or ""
            )
            for item in empreendimentos
        ]

        nomes_nao_vazios = [nome for nome in nomes if nome]

        if len(nomes_nao_vazios) != len(nomes):
            print(
                "AVISO: existem empreendimentos sem nome. "
                "Eles não serão removidos."
            )

        adicionadas, mantidas = atualizar_imagens(empreendimentos)

        # JSON legível e seguro dentro de uma tag script.
        novo_array = json.dumps(
            empreendimentos,
            ensure_ascii=False,
            indent=2,
        )

        trecho_antigo = html_original[
            inicio_marcador + len(MARCADOR_INICIO):fim_marcador
        ]

        trecho_novo = re.sub(
            r"window\s*\.\s*EMPREENDIMENTOS\s*=\s*\[.*?\]\s*;",
            "window.EMPREENDIMENTOS = " + novo_array + ";",
            trecho_antigo,
            count=1,
            flags=re.DOTALL,
        )

        if trecho_novo == trecho_antigo:
            print("ERRO: não consegui atualizar o array do catálogo.")
            return 1

        html_novo = (
            html_original[:inicio_marcador + len(MARCADOR_INICIO)]
            + trecho_novo
            + html_original[fim_marcador:]
        )

        # Verifica se o HTML mantém os marcadores e os dados.
        if MARCADOR_INICIO not in html_novo or MARCADOR_FIM not in html_novo:
            print("ERRO: os marcadores não foram preservados.")
            return 1

        if "window.EMPREENDIMENTOS" not in html_novo:
            print("ERRO: o catálogo desapareceu do HTML.")
            return 1

        # Backup antes de gravar.
        if CRIAR_BACKUP:
            backup = gerar_backup(ARQUIVO_HTML)
            print(f"Backup criado: {backup.name}")

        # Gravação atômica para reduzir risco de arquivo incompleto.
        temporario = ARQUIVO_HTML.with_suffix(".html.tmp")
        temporario.write_text(html_novo, encoding="utf-8")
        temporario.replace(ARQUIVO_HTML)

        print()
        print("ATUALIZAÇÃO CONCLUÍDA")
        print(f"Empreendimentos preservados: {len(empreendimentos)}")
        print(f"Imagens adicionadas: {adicionadas}")
        print(f"Imagens já existentes preservadas: {mantidas}")
        print(f"Arquivo atualizado: {ARQUIVO_HTML.name}")
        print()
        print(
            "Observação: o script não verifica se cada URL de imagem "
            "continua ativa na Econ."
        )

        return 0

    except (OSError, ValueError) as erro:
        print(f"ERRO: {erro}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

