"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const clone = valor => JSON.parse(JSON.stringify(valor));
  const slug = valor => String(valor || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "empreendimento";
  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto) el.textContent = texto;
    return el;
  };
  const urlSegura = valor => {
    if (typeof valor !== "string" || !valor.trim()) return "";
    try { return ["https:", "http:", "file:"].includes(new URL(valor, location.href).protocol) ? valor : ""; }
    catch { return ""; }
  };
  function normalizarDocumento(valor, rascunho = false) {
    const itens = Array.isArray(valor) ? valor : valor && valor.empreendimentos;
    if (!Array.isArray(itens)) throw new Error("O arquivo precisa conter uma lista de empreendimentos.");
    const usados = new Set();
    const empreendimentos = itens.map((item, index) => {
      if (!item || typeof item.nome !== "string" || !item.nome.trim()) throw new Error("Empreendimento " + (index + 1) + " sem nome.");
      const base = slug(item.id || item.nome);
      let id = base, numero = 2;
      while (usados.has(id)) id = base + "-" + numero++;
      usados.add(id);
      const imagens = (Array.isArray(item.imagens) ? item.imagens : item.imagem ? [{ src: item.imagem }] : [])
        .map(img => typeof img === "string" ? { src: img } : img)
        .filter(img => img && urlSegura(img.src))
        .map(img => ({ src: img.src, ...(urlSegura(img.miniatura) ? { miniatura: img.miniatura } : {}),
          ...(Number(img.largura) > 0 ? { largura: Number(img.largura) } : {}),
          ...(Number(img.altura) > 0 ? { altura: Number(img.altura) } : {}),
          ...(typeof img.nomeOriginal === "string" ? { nomeOriginal: img.nomeOriginal } : {}),
          ...(rascunho && typeof img.chaveImportacao === "string" ? { chaveImportacao: img.chaveImportacao } : {}) }));
      return { id, nome: item.nome.trim(), regiao: String(item.regiao || ""), bairro: String(item.bairro || ""),
        status: String(item.status || ""), dormitorios: String(item.dormitorios || ""),
        link: urlSegura(item.link) || "https://www.econconstrutora.com.br/imoveis", imagens,
        ...(item.origem === "econ" ? { origem: "econ", fonteId: String(item.fonteId || item.id) } : {}),
        ...(rascunho && item.automatico ? { automatico: true } : {}) };
    });
    return { versao: 1, atualizadoEm: String(valor.atualizadoEm || ""),
      ...(valor.fonte ? { fonte: String(valor.fonte) } : {}),
      ...(valor.quantidadeImportada ? { quantidadeImportada: Number(valor.quantidadeImportada) } : {}), empreendimentos };
  }

  let publicado;
  try { publicado = normalizarDocumento(window.CATALOGO_BUENOS); }
  catch (erro) { $("mensagem").textContent = erro.message + " Confira se catalogo-dados.js está nesta pasta."; return; }
  let documento = clone(publicado);
  let arquivos = new Map(); // Blobs binários, sem base64 ou localStorage.
  const previews = new Map();
  let db;
  let ocupado = false;
  let alterado = false;
  let bytesOriginais = 0;
  let importadas = 0;
  let salvarTimer;
  let ultimaGravacao = Promise.resolve();
  let limiteVisivel = 12;
  const expandidos = new Set();
  const estados = ["", "Lançamento", "Breve Lançamento", "Futuro Lançamento", "Em Construção", "Pronto para Morar"];

  function abrirBanco() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("buenos-fotos-" + location.pathname, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("rascunho");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error("Rascunho aberto em outra janela."));
    });
  }
  function lerRascunho() {
    return new Promise((resolve, reject) => {
      const request = db.transaction("rascunho").objectStore("rascunho").get("atual");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  function persistir() {
    if (!db) return Promise.resolve();
    const dados = { documento: clone(documento), arquivos: Array.from(arquivos), bytesOriginais, importadas, base: JSON.stringify(publicado) };
    ultimaGravacao = ultimaGravacao.catch(() => {}).then(() => new Promise((resolve, reject) => {
      const tx = db.transaction("rascunho", "readwrite");
      tx.objectStore("rascunho").put(dados, "atual");
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Não foi possível salvar o rascunho."));
    })).catch(() => {
      $("mensagem").textContent = "O navegador não guardou o rascunho. Baixe o ZIP antes de fechar esta página.";
    });
    return ultimaGravacao;
  }
  function salvarDepois() {
    alterado = true;
    clearTimeout(salvarTimer);
    salvarTimer = setTimeout(persistir, 400);
  }
  function definirOcupado(valor) {
    ocupado = valor;
    document.querySelectorAll("input,select,button").forEach(el => { el.disabled = valor; });
    $("area-upload").setAttribute("aria-busy", String(valor));
  }
  function caminhoPreview(imagem) {
    const caminho = imagem.miniatura || imagem.src;
    if (arquivos.has(caminho)) {
      if (!previews.has(caminho)) previews.set(caminho, URL.createObjectURL(arquivos.get(caminho)));
      return previews.get(caminho);
    }
    return urlSegura(caminho);
  }
  function limparPreviews() { previews.forEach(url => URL.revokeObjectURL(url)); previews.clear(); }
  function coletarArquivos() {
    const usados = new Set(documento.empreendimentos.flatMap(item => item.imagens.flatMap(img => [img.src, img.miniatura].filter(Boolean))));
    for (const caminho of arquivos.keys()) {
      if (!usados.has(caminho)) {
        arquivos.delete(caminho);
        if (previews.has(caminho)) { URL.revokeObjectURL(previews.get(caminho)); previews.delete(caminho); }
      }
    }
  }
  function resumir() {
    const total = documento.empreendimentos.reduce((soma, item) => soma + item.imagens.length, 0);
    const bytes = Array.from(arquivos.values()).reduce((soma, blob) => soma + blob.size, 0);
    $("resumo").textContent = documento.empreendimentos.length + " empreendimentos · " + total + " fotos" +
      (arquivos.size ? " · " + (bytes / 1048576).toFixed(1) + " MB de arquivos novos" : "");
  }
  function campo(item, nome, legenda, tipo = "text") {
    const label = criar("label", "campo", legenda);
    const entrada = criar(tipo === "select" ? "select" : "input");
    if (tipo !== "select") entrada.type = tipo;
    if (tipo === "select") {
      const opcoes = new Set([...estados, item[nome]]);
      opcoes.forEach(valor => { const opcao = criar("option", "", valor || "Informar no atendimento"); opcao.value = valor; entrada.append(opcao); });
    }
    entrada.value = item[nome] || "";
    entrada.dataset.campo = nome;
    entrada.addEventListener("change", () => {
      item[nome] = entrada.value.trim();
      if (nome === "nome") {
        if (!item.nome) { item.nome = "Novo empreendimento"; entrada.value = item.nome; }
        renderizar();
      }
      salvarDepois();
    });
    label.append(entrada);
    return label;
  }
  function renderizar() {
    const fragmento = document.createDocumentFragment();
    const termo = slug($("busca-editor").value || "");
    const filtrados = documento.empreendimentos.filter(item => !$("busca-editor").value.trim() || slug([item.nome, item.bairro, item.regiao].join(" ")).includes(termo));
    filtrados.slice(0, limiteVisivel).forEach(item => {
      const secao = criar("section", "projeto"); secao.dataset.id = item.id;
      const topo = criar("div", "projeto-cabecalho");
      const titulo = criar("div"); titulo.append(criar("h3", "", item.nome), criar("small", "", item.imagens.length + " foto(s) · a primeira é a capa"));
      const remover = criar("button", "link-botao", "Remover empreendimento"); remover.type = "button";
      remover.onclick = () => {
        if (!confirm('Remover "' + item.nome + '" deste rascunho? O site publicado só muda depois da atualização.')) return;
        documento.empreendimentos = documento.empreendimentos.filter(outro => outro !== item);
        coletarArquivos(); renderizar(); salvarDepois();
      };
      topo.append(titulo, remover);
      const campos = criar("div", "campos");
      campos.append(campo(item, "nome", "Nome do empreendimento"), campo(item, "bairro", "Bairro"), campo(item, "regiao", "Região"),
        campo(item, "status", "Estágio", "select"), campo(item, "dormitorios", "Dormitórios"), campo(item, "link", "Link oficial", "url"));
      const miniaturas = criar("div", "miniaturas");
      item.imagens.slice(0, expandidos.has(item.id) ? item.imagens.length : 3).forEach((imagem, indice) => {
        const bloco = criar("div", "miniatura");
        const img = criar("img"); img.alt = "Foto " + (indice + 1) + " de " + item.nome; img.loading = "lazy"; img.decoding = "async";
        const semPreview = criar("span", "sem-preview", arquivos.has(imagem.src) ? "Prévia indisponível" : "Foto já cadastrada · prévia depende do arquivo original");
        semPreview.hidden = true;
        img.onerror = () => { img.hidden = true; semPreview.hidden = false; };
        img.src = caminhoPreview(imagem);
        const controles = criar("div", "foto-controles");
        controles.append(criar("small", "", imagem.nomeOriginal || imagem.src.split("/").pop()));
        const botoes = criar("div", "foto-botoes");
        const capa = criar("button", "capa", indice === 0 ? "✓ Capa" : "Usar como capa"); capa.type = "button";
        capa.setAttribute("aria-pressed", String(indice === 0));
        capa.onclick = () => { item.imagens.splice(indice, 1); item.imagens.unshift(imagem); renderizar(); salvarDepois(); };
        const excluir = criar("button", "link-botao", "Remover"); excluir.type = "button";
        excluir.setAttribute("aria-label", "Remover foto " + (indice + 1) + " de " + item.nome);
        excluir.onclick = () => { item.imagens.splice(indice, 1); coletarArquivos(); renderizar(); salvarDepois(); };
        botoes.append(capa, excluir);
        const vinculo = criar("label", "vinculo", "Vincular ao empreendimento:");
        const select = criar("select");
        documento.empreendimentos.forEach(outro => { const option = criar("option", "", outro.nome); option.value = outro.id; select.append(option); });
        select.value = item.id;
        select.onchange = () => {
          const destino = documento.empreendimentos.find(outro => outro.id === select.value);
          if (!destino || destino === item) return;
          item.imagens.splice(indice, 1); destino.imagens.push(imagem);
          // Rascunhos criados automaticamente, sem outras fotos, não viram anúncios vazios.
          if (item.automatico && item.imagens.length === 0) documento.empreendimentos = documento.empreendimentos.filter(outro => outro !== item);
          renderizar(); salvarDepois();
        };
        vinculo.append(select); controles.append(botoes, vinculo); bloco.append(img, semPreview, controles); miniaturas.append(bloco);
      });
      secao.append(topo, campos);
      secao.append(item.imagens.length ? miniaturas : criar("p", "sem-fotos", "Adicione fotos no topo da página. Depois, vincule cada foto a este empreendimento."));
      if (item.imagens.length > 3) {
        const mostrar = criar("button", "botao secundario mais-fotos", expandidos.has(item.id) ? "Recolher fotos" : "Mostrar todas as " + item.imagens.length + " fotos");
        mostrar.type = "button";
        mostrar.onclick = () => { if (expandidos.has(item.id)) expandidos.delete(item.id); else expandidos.add(item.id); renderizar(); };
        secao.append(mostrar);
      }
      fragmento.append(secao);
    });
    if (!filtrados.length) fragmento.append(criar("p", "sem-fotos", "Nenhum empreendimento encontrado."));
    $("lista").replaceChildren(fragmento); $("mostrar-mais").hidden = filtrados.length <= limiteVisivel; resumir();
  }

  function novoItem(nome, automatico = false) {
    const base = slug(nome);
    let id = base, numero = 2;
    while (documento.empreendimentos.some(item => item.id === id)) id = base + "-" + numero++;
    const item = { id, nome, bairro: "", regiao: "", status: "", dormitorios: "", link: "https://www.econconstrutora.com.br/imoveis", imagens: [] };
    if (automatico) item.automatico = true;
    documento.empreendimentos.push(item);
    return item;
  }
  function acharDestino(nomeArquivo) {
    let nome = nomeArquivo.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
    const comparavel = slug(nome);
    const candidatos = documento.empreendimentos.filter(item => comparavel === slug(item.nome) || comparavel.startsWith(slug(item.nome) + "-"))
      .sort((a, b) => b.nome.length - a.nome.length);
    if (candidatos.length) return candidatos[0];
    nome = nome.replace(/\s*(?:\(\d+\)|\d+)$/, "").replace(/\s+(fachada|piscina|lazer|planta|quarto|sala|foto|imagem)$/i, "").trim() || "Novo empreendimento";
    const igual = documento.empreendimentos.find(item => slug(item.nome) === slug(nome));
    return igual || novoItem(nome, true);
  }
  function carregarImagem(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file), img = new Image();
      img.onload = () => resolve({ img, liberar: () => { img.src = ""; URL.revokeObjectURL(url); } });
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("não foi possível ler a imagem. Para HEIC, salve em JPG.")); };
      img.src = url;
    });
  }
  function reduzir(img, limite, qualidade) {
    const escala = Math.min(1, limite / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * escala));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * escala));
    const largura = canvas.width, altura = canvas.height;
    const contexto = canvas.getContext("2d");
    if (!contexto) throw new Error("o navegador não conseguiu preparar a imagem.");
    contexto.drawImage(img, 0, 0, largura, altura);
    return new Promise((resolve, reject) => canvas.toBlob(blob => {
      canvas.width = canvas.height = 1;
      if (!blob) { reject(new Error("não foi possível otimizar a imagem.")); return; }
      resolve({ blob, largura, altura, ext: blob.type === "image/webp" ? "webp" : "png" });
    }, "image/webp", qualidade));
  }
  async function importarFotos(lista) {
    if (ocupado || !lista.length) return;
    definirOcupado(true); clearTimeout(salvarTimer);
    $("erros").replaceChildren(); $("erros").hidden = true;
    $("progresso").hidden = false; $("progresso").max = lista.length; $("progresso").value = 0;
    let sucesso = 0, repetidas = 0, falhas = 0;
    try {
      for (let index = 0; index < lista.length; index++) {
        const file = lista[index];
        $("mensagem").textContent = "Preparando " + (index + 1) + " de " + lista.length + ": " + file.name;
        let original;
        try {
          if (!file.size) throw new Error("o arquivo está vazio.");
          if (!file.type.startsWith("image/") && !/\.(jpe?g|png|webp|avif|gif|bmp|heic|heif)$/i.test(file.name)) throw new Error("selecione um arquivo de imagem.");
          const chave = file.name + "|" + file.size + "|" + file.lastModified;
          if (documento.empreendimentos.some(item => item.imagens.some(img => img.chaveImportacao === chave))) { repetidas++; continue; }
          original = await carregarImagem(file);
          const grande = await reduzir(original.img, 1200, .82);
          const pequena = await reduzir(original.img, 640, .78);
          const destino = acharDestino(file.name);
          const identificador = Date.now().toString(36) + "-" + index.toString(36) + "-" + Math.random().toString(36).slice(2, 7);
          const base = "images/" + slug(file.name.replace(/\.[^.]+$/, "")).slice(0, 80) + "-" + identificador;
          const src = base + "." + grande.ext, miniatura = base + "-640." + pequena.ext;
          arquivos.set(src, grande.blob); arquivos.set(miniatura, pequena.blob);
          destino.imagens.push({ src, miniatura, largura: grande.largura, altura: grande.altura, nomeOriginal: file.name, chaveImportacao: chave });
          bytesOriginais += file.size; importadas++; sucesso++; alterado = true;
        } catch (erro) {
          falhas++; $("erros").hidden = false;
          $("erros").append(criar("li", "", file.name + ": " + erro.message));
        } finally {
          if (original) original.liberar();
          $("progresso").value = index + 1;
        }
      }
      renderizar();
      $("mensagem").textContent = sucesso + " foto(s) adicionada(s)" + (repetidas ? " · " + repetidas + " repetida(s) ignorada(s)" : "") + (falhas ? " · " + falhas + " arquivo(s) precisam de atenção" : "") + ". Confira os vínculos e baixe a atualização.";
      await persistir();
    } finally { definirOcupado(false); $("progresso").hidden = true; $("arquivos").value = ""; }
  }

  function dadosPublicos() {
    const copia = clone(documento);
    copia.atualizadoEm = new Date().toISOString();
    copia.empreendimentos.forEach(item => {
      delete item.automatico;
      item.imagens.forEach(img => { delete img.chaveImportacao; });
    });
    return copia;
  }
  async function exportar() {
    if (ocupado) return;
    definirOcupado(true); clearTimeout(salvarTimer);
    try {
      const dados = dadosPublicos();
      if (!dados.empreendimentos.length) throw new Error("Adicione pelo menos um empreendimento antes de baixar.");
      if (!window.JSZip) throw new Error("A pasta vendor precisa estar ao lado desta página. Extraia o ZIP completo do site antes de usar o organizador.");
      coletarArquivos();
      const zip = new JSZip();
      const json = JSON.stringify(dados, null, 2);
      zip.file("catalogo-dados.js", "/* Gerado pelo organizador Buenos SP. */\nwindow.CATALOGO_BUENOS = " + json.replace(/</g, "\\u003c") + ";\n");
      zip.file("catalogo-dados.json", json + "\n");
      arquivos.forEach((blob, caminho) => zip.file(caminho, blob));
      zip.file("COMO-APLICAR.txt", "ATUALIZAÇÃO DO CATÁLOGO BUENOS SP\n\n1. Extraia este ZIP.\n2. Copie catalogo-dados.js para a pasta principal do site, substituindo a versão anterior.\n3. Mescle a pasta images com a pasta images do site. Preserve as fotos que já estavam lá.\n4. Envie catalogo-dados.js e os novos arquivos de images para sua hospedagem.\n5. Atualize empreendimentos.html com Ctrl + F5.\n\nEste ZIP contém a atualização de fotos e catálogo, não o site completo. Use-o junto ao pacote corrigido do site.\nGuarde-o como cópia de segurança. O JSON serve para reimportar o catálogo no organizador; o site lê o JS.\n");
      $("mensagem").textContent = "Gerando seu ZIP…";
      // Imagens WebP já são compactadas. STORE evita processamento extra no celular.
      const blob = await zip.generateAsync({ type: "blob", compression: "STORE" });
      const url = URL.createObjectURL(blob), link = criar("a");
      link.href = url; link.download = "atualizacao-buenos-sp.zip";
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      alterado = false;
      $("mensagem").textContent = "ZIP pronto. Extraia e envie catalogo-dados.js e a pasta images para o site, seguindo as instruções abaixo.";
      await persistir();
    } catch (erro) { $("mensagem").textContent = erro.message; }
    finally { definirOcupado(false); }
  }
  async function importarCatalogo(file) {
    if (!file || ocupado) return;
    definirOcupado(true); clearTimeout(salvarTimer);
    try {
      let dados, novosArquivos = new Map(), aviso = "";
      if (/\.zip$/i.test(file.name)) {
        if (!window.JSZip) throw new Error("A pasta vendor precisa estar na mesma pasta do organizador.");
        const zip = await JSZip.loadAsync(file);
        const json = zip.file("catalogo-dados.json");
        if (!json) throw new Error("Use um ZIP exportado por este organizador, com catalogo-dados.json na raiz.");
        dados = normalizarDocumento(JSON.parse(await json.async("string")));
        for (const item of dados.empreendimentos) for (const imagem of item.imagens) for (const caminho of [imagem.src, imagem.miniatura].filter(Boolean)) {
          if (!/^images\/[a-zA-Z0-9_./-]+\.(webp|png|jpe?g|avif)$/i.test(caminho) || caminho.split("/").includes("..")) continue;
          const entrada = zip.file(caminho);
          if (entrada) novosArquivos.set(caminho, await entrada.async("blob"));
        }
      } else {
        dados = normalizarDocumento(JSON.parse(await file.text()));
        if (dados.empreendimentos.some(item => item.imagens.some(img => img.src.startsWith("images/")))) {
          aviso = " Para recuperar também fotos novas, importe o ZIP completo do organizador.";
        }
      }
      const mapa = new Map(documento.empreendimentos.map(item => [item.id, item]));
      dados.empreendimentos.forEach(item => mapa.set(item.id, item));
      documento.empreendimentos = Array.from(mapa.values());
      novosArquivos.forEach((blob, caminho) => arquivos.set(caminho, blob));
      limparPreviews(); coletarArquivos(); renderizar(); alterado = true;
      $("mensagem").textContent = "Catálogo importado. Confira os empreendimentos e baixe a atualização quando terminar." + aviso;
      await persistir();
    } catch (erro) { $("mensagem").textContent = "Não foi possível importar: " + erro.message; }
    finally { definirOcupado(false); $("importar").value = ""; }
  }
  $("arquivos").addEventListener("change", event => importarFotos(Array.from(event.target.files)));
  $("baixar").onclick = exportar;
  $("novo").onclick = () => { novoItem("Novo empreendimento"); $("busca-editor").value = "Novo empreendimento"; limiteVisivel = 12; renderizar(); salvarDepois(); $("lista").lastElementChild.scrollIntoView({ behavior: "smooth", block: "start" }); };
  $("busca-editor").addEventListener("input", () => { limiteVisivel = 12; renderizar(); });
  $("mostrar-mais").onclick = () => { limiteVisivel += 12; renderizar(); };
  $("importar").onchange = event => importarCatalogo(event.target.files[0]);
  $("restaurar").onclick = async () => {
    if (!confirm("Descartar o rascunho e voltar ao catálogo que acompanha esta página? Guarde seu ZIP antes de continuar.")) return;
    documento = clone(publicado); arquivos.clear(); limparPreviews(); importadas = 0; bytesOriginais = 0;
    clearTimeout(salvarTimer); alterado = false; renderizar();
    $("mensagem").textContent = "Catálogo publicado restaurado."; await persistir();
  };
  const upload = $("area-upload");
  ["dragenter", "dragover"].forEach(nome => upload.addEventListener(nome, event => { event.preventDefault(); if (!ocupado) upload.classList.add("arrastando"); }));
  ["dragleave", "drop"].forEach(nome => upload.addEventListener(nome, event => { event.preventDefault(); upload.classList.remove("arrastando"); }));
  upload.addEventListener("drop", event => importarFotos(Array.from(event.dataTransfer.files)));
  window.addEventListener("beforeunload", event => { if (ocupado || alterado) { event.preventDefault(); event.returnValue = ""; } });

  (async () => {
    definirOcupado(true);
    let mensagem = "Selecione suas fotos para começar. Você pode adicionar todas de uma vez.";
    try {
      db = await abrirBanco();
      const salvo = await lerRascunho();
      if (salvo && salvo.base === JSON.stringify(publicado)) {
        documento = normalizarDocumento(salvo.documento, true); arquivos = new Map(salvo.arquivos || []);
        bytesOriginais = salvo.bytesOriginais || 0; importadas = salvo.importadas || 0;
        mensagem = "Seu rascunho anterior foi recuperado. Confira as fotos e baixe a atualização quando terminar.";
      } else if (salvo) {
        mensagem = "O catálogo publicado foi atualizado. Se precisar recuperar um rascunho antigo, importe o ZIP que você salvou.";
      }
    } catch {
      mensagem = "Selecione suas fotos. Neste navegador, guarde o ZIP antes de fechar a página: o rascunho pode não ser preservado.";
    }
    renderizar(); definirOcupado(false); $("mensagem").textContent = mensagem;
  })();
})();
