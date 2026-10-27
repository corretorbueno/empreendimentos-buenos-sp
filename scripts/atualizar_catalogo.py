#!/usr/bin/env python3
"""Importa TODOS os dados públicos enviados pela página da Econ, não só os cards visíveis.

Uso: python scripts/atualizar_catalogo.py
Dependência para salvar capas locais: python -m pip install Pillow
Não é necessário backend para exibir o catálogo gerado.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

URL = "https://www.econconstrutora.com.br/imoveis"
RAIZ = Path(__file__).resolve().parents[1]
ESTAGIOS = {
    "lancamento": "Lançamento", "breve-lancamento": "Breve Lançamento",
    "em-construcao": "Em Construção", "pronto-para-morar": "Pronto para Morar",
    "futuro-lancamento": "Futuro Lançamento",
}


def slug(texto):
    texto = unicodedata.normalize("NFD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9_-]", "", re.sub(r"\s+", "-", texto))


def obter(url):
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("Endereço inválido")
    url = quote(url, safe=":/?&=%+#@;,!$'()*[]")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (Catalogo Buenos SP)", "Accept": "*/*"})
    for tentativa in range(3):
        try:
            with urlopen(request, timeout=35) as resposta:
                return resposta.read()
        except (HTTPError, URLError) as erro:
            if tentativa == 2 or (isinstance(erro, HTTPError) and erro.code not in {429, 500, 502, 503, 504}):
                raise
            time.sleep(tentativa + 1)


def extrair_empreendimentos(html):
    # O App Router entrega a lista completa dentro dos blocos de dados do React.
    # Não executar scripts: decodificar somente os arrays/objetos JSON necessários.
    chunks = []
    for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            bloco = json.loads(match.group(1))
        except (ValueError, TypeError):
            continue
        if isinstance(bloco, list) and len(bloco) > 1 and bloco[0] == 1 and isinstance(bloco[1], str):
            chunks.append(bloco[1])
    dados = "".join(chunks)
    decoder = json.JSONDecoder()
    listas = []
    for match in re.finditer(r'"initialProperties"\s*:', dados):
        try:
            lista, _ = decoder.raw_decode(dados[match.end():].lstrip())
        except ValueError:
            continue
        if isinstance(lista, list) and all(isinstance(item, dict) for item in lista):
            listas.append(lista)
    if not listas:
        raise RuntimeError("A estrutura da Econ mudou: initialProperties não foi encontrado. O catálogo atual foi preservado.")
    lista = max(listas, key=len)
    resultado = {}
    for item in lista:
        if item.get("ativo") is False or not item.get("titulo") or not item.get("slug"):
            continue
        resultado[str(item.get("_id") or item["slug"])] = item
    if len(resultado) < 10:
        raise RuntimeError("A Econ retornou poucos registros. Nenhum catálogo foi sobrescrito.")
    return list(resultado.values())


def endereco_imagem(valor):
    return valor if isinstance(valor, str) and urlsplit(valor).scheme in {"http", "https"} else ""


def transformar(item):
    local = item.get("localizacao") or {}
    fotos = [foto for foto in item.get("fotos", []) if endereco_imagem(foto.get("path"))]
    capa = (endereco_imagem(item.get("new_thumb"))
            or endereco_imagem((item.get("thumbnail") or {}).get("path"))
            or next((foto["path"] for foto in fotos if foto.get("banner")), "")
            or (fotos[0]["path"] if fotos else ""))
    imagens = []
    vistos = set()
    for foto in ([{"path": capa, "texto": "Capa"}] if capa else []) + fotos:
        if foto["path"] not in vistos:
            imagens.append({"src": foto["path"]})
            vistos.add(foto["path"])
    quartos = sorted({int(q["qtde"]) for q in item.get("quartos", []) if str(q.get("qtde", "")).isdigit()})
    return {
        "id": slug(item["slug"]), "fonteId": str(item.get("_id") or item["slug"]), "origem": "econ",
        "nome": re.sub(r"\s+", " ", item["titulo"]).strip(),
        "regiao": str(local.get("zona") or "").strip(), "bairro": str(local.get("bairro") or "").strip(),
        "status": ESTAGIOS.get(item.get("categoria"), str(item.get("categoria") or "").replace("-", " ").capitalize()),
        "dormitorios": " e ".join(map(str, quartos)) + " dorms." if quartos else "",
        "link": "https://www.econconstrutora.com.br/imovel/" + slug(local.get("zona") or "grande-sp") + "/" + quote(item["slug"], safe="-_"),
        "imagens": imagens,
    }


def salvar_capa(url):
    from PIL import Image, ImageOps

    pasta = RAIZ / "images" / "econ"
    pasta.mkdir(parents=True, exist_ok=True)
    chave = sha256(url.encode()).hexdigest()[:20]
    grande = pasta / f"{chave}-1200.webp"
    miniatura = pasta / f"{chave}-640.webp"
    if not grande.exists() or not miniatura.exists():
        with Image.open(BytesIO(obter(url))) as original:
            imagem = ImageOps.exif_transpose(original)
            imagem = imagem.convert("RGBA" if "A" in imagem.getbands() else "RGB")
            for caminho, limite, qualidade in [(grande, 1200, 82), (miniatura, 640, 78)]:
                copia = imagem.copy()
                copia.thumbnail((limite, limite), Image.Resampling.LANCZOS)
                temporario = caminho.with_suffix(".webp.tmp")
                copia.save(temporario, "WEBP", quality=qualidade, method=5)
                temporario.replace(caminho)
    with Image.open(grande) as foto:
        largura, altura = foto.size
    return {"src": grande.relative_to(RAIZ).as_posix(), "miniatura": miniatura.relative_to(RAIZ).as_posix(),
            "largura": largura, "altura": altura, "fonte": url}


def ler_atual():
    caminho = RAIZ / "catalogo-dados.js"
    if not caminho.exists():
        return {"empreendimentos": []}
    texto = caminho.read_text(encoding="utf-8")
    match = re.search(r"window\.CATALOGO_BUENOS\s*=\s*(.*?);?\s*$", texto, re.S)
    if not match:
        raise RuntimeError("catalogo-dados.js inválido. Corrija o arquivo antes de atualizar.")
    return json.loads(match.group(1).rstrip().removesuffix(";"))


def escrever_json(caminho, dados, prefixo="", sufixo="\n"):
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    temporario.write_text(prefixo + texto + sufixo, encoding="utf-8")
    temporario.replace(caminho)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html-local", type=Path, help="Usar uma cópia já obtida da página, para verificação")
    parser.add_argument("--sem-baixar-imagens", action="store_true", help="Manter referências remotas das capas")
    parser.add_argument("--permitir-reducao", action="store_true", help="Aceitar uma redução superior a 20%% após conferir a fonte")
    args = parser.parse_args()
    atual = ler_atual()
    html = args.html_local.read_text(encoding="utf-8") if args.html_local else obter(URL).decode("utf-8")
    fonte = extrair_empreendimentos(html)
    anteriores_econ = [p for p in atual.get("empreendimentos", []) if p.get("origem") == "econ"]
    if anteriores_econ and len(fonte) < .8 * len(anteriores_econ) and not args.permitir_reducao:
        raise RuntimeError("A lista retornou mais de 20% menor. Catálogo preservado. Confira a fonte antes de aceitar a redução.")
    # Reproduzir a ordenação da página: lançamento mais recente primeiro.
    fonte.sort(key=lambda p: (p.get("ano_lancamento") or 0, p.get("mes_lancamento") or 1), reverse=True)
    projetos = [transformar(item) for item in fonte]
    avisos = []
    capas = {}
    urls = {p["imagens"][0]["src"] for p in projetos if p["imagens"]}
    if not args.sem_baixar_imagens:
        with ThreadPoolExecutor(max_workers=6) as pool:
            tarefas = {pool.submit(salvar_capa, url): url for url in urls}
            for numero, futuro in enumerate(as_completed(tarefas), 1):
                url = tarefas[futuro]
                try:
                    capas[url] = futuro.result()
                except Exception as erro:
                    avisos.append({"imagem": url, "motivo": str(erro)})
                if numero % 20 == 0 or numero == len(urls):
                    print(f"Capas verificadas: {numero}/{len(urls)}", flush=True)
    existentes = {p.get("fonteId") or p["id"]: p for p in atual.get("empreendimentos", [])}
    for projeto in projetos:
        if projeto["imagens"] and projeto["imagens"][0]["src"] in capas:
            projeto["imagens"][0] = capas[projeto["imagens"][0]["src"]]
        anterior = existentes.get(projeto["fonteId"]) or existentes.get(projeto["id"])
        if anterior:
            manuais = [img for img in anterior.get("imagens", []) if isinstance(img, dict)
                       and img.get("src", "").startswith("images/") and not img.get("src", "").startswith("images/econ/")]
            projeto["imagens"] = manuais + projeto["imagens"]
    ids = {p["id"] for p in projetos}
    # Cadastros manuais não são apagados pelo importador.
    projetos.extend(p for p in atual.get("empreendimentos", []) if p.get("origem") != "econ" and p.get("id") not in ids)
    documento = {"versao": 1, "atualizadoEm": datetime.now(timezone.utc).isoformat(), "fonte": URL,
                 "quantidadeImportada": len(fonte), "empreendimentos": projetos}
    escrever_json(RAIZ / "catalogo-dados.js", documento,
                  "/* Importado do catálogo público da Econ. */\nwindow.CATALOGO_BUENOS = ", ";\n")
    relatorio = {"fonte": URL, "atualizadoEm": documento["atualizadoEm"], "empreendimentosImportados": len(fonte),
                 "fotosReferenciadas": sum(len(p["imagens"]) for p in projetos), "capasDistintasSalvas": len(capas),
                 "capasComFalha": avisos}
    escrever_json(RAIZ / "relatorio-importacao.json", relatorio)
    print(json.dumps({k: v for k, v in relatorio.items() if k != "capasComFalha"}, ensure_ascii=False, indent=2))
    if avisos:
        print(f"ATENÇÃO: {len(avisos)} capa(s) permaneceram remotas. Confira relatorio-importacao.json.")


if __name__ == "__main__":
    main()
