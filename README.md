# Empreendimentos Buenos SP — site corrigido

Abra **LEIA-ME.html** para ver as instruções de uso.

## O que estava errado

- `empreendimentos (2).html` tinha uma lista fixa de **10 empreendimentos**, começando na linha 677. A lista terminava na linha 759. Não havia uma rotina de importação das outras fotos.
- O script antigo procurava títulos visíveis (`h2`, `h3`, `h4`). A Econ mostra inicialmente 12 cards e envia a lista completa em seus dados de página (`initialProperties`); o restante entra durante a navegação. Ler só os títulos perde os demais registros.
- O script gerava `empreendimentos.json`, mas a página não carregava esse arquivo. Mesmo uma execução bem-sucedida não atualizaria o catálogo exibido.
- No ZIP recebido, os nomes `index (1).html`, `app (1).js` e `styles (1).css` eram diferentes dos nomes usados nos links (`index.html`, `app.js` e `styles.css`). Esses caminhos foram padronizados. Se os nomes sem sufixos já estavam certos na hospedagem, essa divergência era específica da cópia enviada.
- A pasta `SCRIPT` não correspondia a `scripts/atualizar_catalogo.py`, caminho chamado pelo workflow; `WORKFLOW` também não era a pasta `.github/workflows` esperada pelo GitHub. O workflow continha ainda um bloco duplicado de commit e push.
- Regras CSS com `display: block` e `display: flex` anulavam o atributo `hidden` da imagem e do substituto. Isso foi corrigido para evitar foto quebrada e conteúdo sobreposto.

## O que esta versão entrega

O catálogo público consultado em **27/10/2026** contém **178 empreendimentos ativos no cadastro da fonte**, sem equivaler a uma confirmação de estoque disponível. Todos foram importados, com nome, bairro, região, estágio, dormitórios e link individual da Econ.

As capas foram copiadas para `images/econ` e convertidas para WebP em dois tamanhos: até 640 px para os cards e até 1200 px para a ampliação. URLs repetidas usam os mesmos arquivos. As demais fotos de cada galeria continuam apontando para a Econ e são carregadas quando a galeria é aberta; não é preciso baixar milhares de imagens para visitar o catálogo.

A página lê `catalogo-dados.js`, que também é o arquivo atualizado pelo importador e pelo organizador. Há filtros por texto (com ou sem acentos), estágio, região e dormitórios. As capas carregam conforme a rolagem, com espaço reservado para evitar saltos na página.

O total exato e eventuais falhas constam em `relatorio-importacao.json`.

## Abrir e publicar

1. Extraia o ZIP completo. Não tente usar os HTMLs dentro do ZIP.
2. Abra `index.html` para ver o início ou `empreendimentos.html` para ver o catálogo.
3. Copie o **conteúdo** desta pasta para a pasta principal do site na hospedagem. Mantenha os nomes e a estrutura de subpastas.
4. Substitua os arquivos antigos com os mesmos nomes. Mescle a pasta `images`, preservando outras imagens existentes.
5. Atualize o navegador com **Ctrl + F5**. Em celulares, recarregue a página; se houver cache da hospedagem, atualize-o também.

Não precisa de Node, banco de dados nem servidor Python para exibir o site. Ele é estático e também pode ser conferido localmente com dois cliques nos arquivos HTML. O contato comercial original, pelo WhatsApp `(11) 94516-7897`, foi preservado.

## Atualizar novamente a partir da Econ

Esta entrega contém uma consulta já realizada. O site não faz scraping no navegador de cada visitante.

### Se usa GitHub

Envie também `.github/workflows/atualizar-catalogo.yml` e `scripts/atualizar_catalogo.py` ao repositório. Em **Actions → Atualizar catálogo completo da Econ → Run workflow**, execute a atualização. O workflow salva o catálogo e as capas no repositório; sua hospedagem deve estar configurada para publicar essas alterações.

O workflow é acionado manualmente. Não foi criada uma rotina agendada. Pode ser necessário habilitar permissão de escrita em **Settings → Actions → General → Workflow permissions** no repositório.

### No computador de quem mantém o site

Com Python e Pillow instalados, executar na pasta do site:

```bash
python -m pip install Pillow
python scripts/atualizar_catalogo.py
```

Depois, enviar `catalogo-dados.js`, `relatorio-importacao.json` e `images/econ` atualizados para a hospedagem.

O importador decodifica somente JSON, sem executar JavaScript remoto. Valida a lista antes de substituir o catálogo, interrompe se ela vier mais de 20% menor e reaproveita capas já baixadas. Se a estrutura pública da Econ mudar, o importador avisa e preserva o catálogo anterior. Cadastros manuais e fotos adicionadas em `images/` fora de `images/econ/` são preservados na próxima importação; dados comerciais da Econ voltam a seguir a fonte.

## Adicionar fotos próprias (opcional)

Abra `gerenciar-imagens.html`. Selecione várias imagens, confira a associação de cada foto ao empreendimento, escolha a capa e clique em **Baixar atualização (.zip)**. Extraia esse ZIP e copie `catalogo-dados.js` e os arquivos da pasta `images` para o site.

O ZIP do organizador contém uma **atualização**, não uma cópia completa do site. Mescle sua pasta de imagens com a existente. O gerenciador processa os arquivos em sequência, usa Blobs em vez de base64/localStorage e tenta guardar o rascunho com IndexedDB. Guarde sempre o ZIP exportado. Se o navegador não preservar rascunhos, ele avisa.

O organizador não envia arquivos para a hospedagem e não usa senha. Se você o publicar, visitantes poderão gerar cópias próprias do catálogo, mas isso não altera os arquivos do seu servidor. Não há link para o organizador na navegação pública.

## Arquivos principais

| Arquivo/pasta | Função |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | Página inicial e contato |
| `empreendimentos.html`, `catalogo.css`, `catalogo.js` | Catálogo, filtros e galerias |
| `catalogo-dados.js` | Fonte única dos dados publicados |
| `images/econ/` | Capas importadas e otimizadas |
| `gerenciar-imagens.html`, `gerenciador.css`, `gerenciador.js` | Organização opcional das fotos próprias |
| `scripts/atualizar_catalogo.py` | Nova importação da Econ |
| `.github/workflows/atualizar-catalogo.yml` | Atualização manual via GitHub |
| `privacidade.html` | Política de privacidade fornecida no original |
| `vendor/` | JSZip e sua licença, usados na exportação local |

As imagens ilustrativas e os dados comerciais podem mudar na fonte. A indicação de disponibilidade deve continuar sendo confirmada durante o atendimento.
