
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from urllib.parse import urljoin

SITE = "https://www.econconstrutora.com.br/imoveis"
HTML_FILE = Path("empreendimentos.html")
JSON_FILE = Path("empreendimentos.json")


class ImagensEcon(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imagens = []
        self.links = []
        self.titulo = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)

        if tag == "img":
            url = a.get("src") or a.get("data-src") or a.get("data-lazy-src")
            if url:
                self.imagens.append(urljoin(SITE, url))

        if tag == "source":
            url = a.get("srcset") or a.get("data-srcset")
            if url:
                self.imagens.append(urljoin(SITE, url.split(",")[0].split()[0]))

        if tag == "a" and a.get("href"):
            self.links.append(urljoin(SITE, a["href"]))


def baixar(url):
    req = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urlopen(req, timeout=30) as resposta:
        return resposta.read().decode("utf-8", errors="replace")


def normalizar(texto):
    return re.sub(r"[^a-z0-9]", "", texto.lower())


pagina = baixar(SITE)
parser = ImagensEcon()
parser.feed(pagina)

imagens = list(dict.fromkeys(parser.imagens))

if not imagens:
    raise RuntimeError(
        "O site não forneceu imagens no HTML. "
        "Pode ser necessário consultar a API usada pela Econ."
    )

if not HTML_FILE.exists():
    raise FileNotFoundError("empreendimentos.html não encontrado.")

html = HTML_FILE.read_text(encoding="utf-8")

inicio = "<!-- CATALOGO_DATA_INICIO -->"
fim = "<!-- CATALOGO_DATA_FIM -->"

if inicio not in html or fim not in html:
    raise RuntimeError("Não encontrei os marcadores do catálogo no HTML.")

antes, restante = html.split(inicio, 1)
bloco, depois = restante.split(fim, 1)

# Registra as imagens encontradas no site oficial.
JSON_FILE.write_text(
    json.dumps(
        {"origem": SITE, "imagens": imagens, "quantidade": len(imagens)},
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

# Não altera os projetos existentes no HTML.
# O arquivo JSON permite verificar as imagens coletadas.
print("Site consultado:", SITE)
print("Imagens encontradas:", len(imagens))
print("Arquivo criado:", JSON_FILE)
print("Atenção: as imagens ainda precisam ser associadas aos projetos.")
