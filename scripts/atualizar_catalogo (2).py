import json
import re
from datetime import datetime, timezone
@@ -10,11 +11,13 @@
URL_CATALOGO = "https://www.econconstrutora.com.br/imoveis"
ARQUIVO_SAIDA = Path("empreendimentos.json")


def texto_limpo(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def main():
    print("Acessando o catálogo da Econ...")
    print("Acessando o catalogo publico da Econ...")

    resposta = requests.get(
        URL_CATALOGO,
@@ -33,27 +36,31 @@ def main():
            continue

        bloco = titulo

        for _ in range(6):
            if bloco.parent is None:
                break

            bloco = bloco.parent

            if bloco.find("img"):
                break

        imagens = bloco.find_all("img")
        imagem = ""

        for img in imagens:
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

@@ -72,8 +79,10 @@ def main():
    lista = list(projetos.values())

    if not lista:
        print("Nenhum empreendimento encontrado. Precisamos verificar como o catálogo carrega os dados.")
        return
        raise RuntimeError(
            "Nenhum empreendimento encontrado. "
            "Precisamos verificar como o catalogo carrega os dados."
        )

    documento = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
@@ -86,8 +95,14 @@ def main():
        encoding="utf-8",
    )

    com_imagem = sum(1 for item in lista if item["imagem"])

    print(f"Empreendimentos encontrados: {len(lista)}")
    print(f"Com imagem: {com_imagem}")
    print(f"Sem imagem: {len(lista) - com_imagem}")
    print(f"Arquivo gerado: {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
