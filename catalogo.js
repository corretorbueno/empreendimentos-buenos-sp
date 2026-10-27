/* O mesmo catálogo é lido pelo site e pelo gerenciador, inclusive sem servidor. */
"use strict";
(() => {
  const grade = document.getElementById("gradeEmpreendimentos");
  const busca = document.getElementById("busca");
  const filtro = document.getElementById("filtroStatus");
  const contador = document.getElementById("contador");
  const regiao = document.getElementById("filtroRegiao");
  const dormitorios = document.getElementById("filtroDormitorios");
  const dialog = document.getElementById("galeria");
  const foto = document.getElementById("galeria-imagem");
  const erro = document.getElementById("galeria-erro");
  const oficial = "https://www.econconstrutora.com.br/imoveis";
  const normalizar = texto => String(texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const endereco = valor => {
    if (typeof valor !== "string" || !valor.trim()) return "";
    try {
      const url = new URL(valor, location.href);
      return ["http:", "https:", "file:"].includes(url.protocol) ? url.href : "";
    } catch { return ""; }
  };
  const elemento = (tipo, classe, texto) => {
    const el = document.createElement(tipo);
    if (classe) el.className = classe;
    if (texto) el.textContent = texto;
    return el;
  };
  let itemGaleria;
  let indiceFoto = 0;
  const imagens = item => (Array.isArray(item.imagens) ? item.imagens : [{ src: item.imagem }])
    .map(img => typeof img === "string" ? { src: img } : img)
    .filter(img => img && endereco(img.src));

  function atualizarGaleria() {
    const lista = imagens(itemGaleria);
    const atual = lista[indiceFoto];
    if (!atual) return;
    erro.hidden = true;
    foto.hidden = false;
    foto.alt = itemGaleria.nome + " — foto " + (indiceFoto + 1);
    foto.src = endereco(atual.src);
    document.getElementById("galeria-contador").textContent = (indiceFoto + 1) + " de " + lista.length;
    document.getElementById("foto-anterior").disabled = lista.length < 2;
    document.getElementById("foto-seguinte").disabled = lista.length < 2;
  }
  foto.onerror = () => { foto.hidden = true; erro.hidden = false; };
  function mudarFoto(passo) {
    if (!itemGaleria) return;
    const total = imagens(itemGaleria).length;
    if (total) { indiceFoto = (indiceFoto + passo + total) % total; atualizarGaleria(); }
  }
  document.getElementById("foto-anterior").onclick = () => mudarFoto(-1);
  document.getElementById("foto-seguinte").onclick = () => mudarFoto(1);
  document.getElementById("fechar-galeria").onclick = () => dialog.close();
  dialog.addEventListener("keydown", event => {
    if (event.key === "ArrowLeft") { event.preventDefault(); mudarFoto(-1); }
    if (event.key === "ArrowRight") { event.preventDefault(); mudarFoto(1); }
  });
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });

  function criarCard(item) {
    const card = elemento("article", "card");
    const container = elemento("div", "foto-container");
    if (item.status) container.append(elemento("span", "status", item.status));
    const fallback = elemento("div", "foto-fallback");
    const simbolo = elemento("span", "predio", "⌂");
    simbolo.setAttribute("aria-hidden", "true");
    fallback.append(simbolo, elemento("strong", "", item.nome), elemento("small", "", "Consulte as imagens no catálogo oficial"));
    const lista = imagens(item);
    const capa = lista[0];
    container.append(fallback);
    if (capa) {
      const abrir = elemento("button", "abrir-fotos");
      abrir.type = "button";
      abrir.setAttribute("aria-label", "Ver fotos de " + item.nome);
      const img = elemento("img");
      img.alt = "Imagem ilustrativa de " + item.nome;
      img.loading = "lazy";
      img.decoding = "async";
      img.width = Number(capa.largura) || 1200;
      img.height = Number(capa.altura) || 900;
      fallback.hidden = true;
      img.onerror = () => { abrir.hidden = true; fallback.hidden = false; };
      img.src = endereco(capa.miniatura || capa.src);
      abrir.append(img, elemento("span", "quantidade-fotos", lista.length === 1 ? "Ver foto ↗" : "Ver " + lista.length + " fotos ↗"));
      abrir.onclick = () => {
        itemGaleria = item; indiceFoto = 0;
        document.getElementById("galeria-titulo").textContent = item.nome;
        atualizarGaleria(); dialog.showModal();
      };
      container.append(abrir);
    }
    const conteudo = elemento("div", "card-conteudo");
    conteudo.append(elemento("h3", "", item.nome));
    const local = [item.regiao, item.bairro].filter(Boolean).join(" • ");
    if (local) conteudo.append(elemento("p", "local", local));
    const detalhes = elemento("div", "detalhes");
    [item.dormitorios, item.status].filter(Boolean).forEach(texto => detalhes.append(elemento("span", "detalhe", texto)));
    const acoes = elemento("div", "card-acoes");
    const whatsapp = elemento("a", "botao botao-whatsapp", "Tenho interesse ↗");
    const mensagem = "Olá! Tenho interesse no empreendimento " + item.nome + (item.bairro ? ", em " + item.bairro : "") + ". Pode me passar mais informações?";
    whatsapp.href = "https://wa.me/5511945167897?text=" + encodeURIComponent(mensagem);
    const link = elemento("a", "link-oficial", "Ver informações oficiais ↗");
    const urlOficial = endereco(item.link);
    link.href = /^https?:/.test(urlOficial) ? urlOficial : oficial;
    [whatsapp, link].forEach(a => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
    acoes.append(whatsapp, link);
    conteudo.append(detalhes, acoes);
    card.append(container, conteudo);
    return card;
  }

  const dados = window.CATALOGO_BUENOS;
  if (!dados || !Array.isArray(dados.empreendimentos)) {
    contador.textContent = "Não foi possível abrir o catálogo. Confira se catalogo-dados.js está na mesma pasta desta página.";
    return;
  }
  const itens = dados.empreendimentos.filter(item => item && typeof item.nome === "string" && item.nome.trim());
  Array.from(new Set(itens.map(item => item.regiao).filter(Boolean))).sort((a, b) => a.localeCompare(b, "pt-BR")).forEach(texto => {
    const option = elemento("option", "", texto); option.value = texto; regiao.append(option);
  });
  if (dados.atualizadoEm) {
    const data = new Date(dados.atualizadoEm);
    if (!Number.isNaN(data.getTime())) document.getElementById("atualizacao").textContent = "Catálogo consultado em " + data.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" }) + ". Confirme a disponibilidade no atendimento.";
  }
  const termos = new Map(itens.map(item => [item, normalizar([item.nome, item.regiao, item.bairro, item.status].join(" "))]));
  const estados = new Set(Array.from(filtro.options, opcao => opcao.value));
  itens.forEach(item => {
    if (item.status && !estados.has(item.status)) {
      const option = elemento("option", "", item.status); option.value = item.status;
      filtro.append(option); estados.add(item.status);
    }
  });
  function renderizar() {
    const termo = normalizar(busca.value.trim());
    const filtrados = itens.filter(item => termos.get(item).includes(termo) && (!filtro.value || item.status === filtro.value) &&
      (!regiao.value || item.regiao === regiao.value) && (!dormitorios.value || (item.dormitorios || "").match(/\d+/g)?.includes(dormitorios.value)));
    const fragmento = document.createDocumentFragment();
    filtrados.forEach(item => fragmento.append(criarCard(item)));
    if (!filtrados.length) fragmento.append(elemento("p", "vazio", "Nenhum empreendimento encontrado. Tente outra busca ou estágio."));
    grade.replaceChildren(fragmento);
    contador.textContent = filtrados.length + (filtrados.length === 1 ? " empreendimento encontrado" : " empreendimentos encontrados");
  }
  let debounce;
  busca.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(renderizar, 120); });
  filtro.addEventListener("change", renderizar);
  regiao.addEventListener("change", renderizar);
  dormitorios.addEventListener("change", renderizar);
  document.getElementById("ano").textContent = new Date().getFullYear();
  renderizar();
})();
