
document.addEventListener("DOMContentLoaded", function () {
  const menuToggle = document.getElementById("menu-toggle");
  const nav = document.getElementById("nav");
  const form = document.getElementById("lead-form");
  const formMessage = document.getElementById("form-message");
  const year = document.getElementById("current-year");

  const whatsappNumber = "5511945167897";

  // Atualiza o ano do rodapé
  if (year) {
    year.textContent = new Date().getFullYear();
  }

  // Menu para celular
  if (menuToggle && nav) {
    menuToggle.addEventListener("click", function () {
      const isOpen = nav.classList.toggle("open");
      menuToggle.setAttribute("aria-expanded", String(isOpen));
      menuToggle.setAttribute(
        "aria-label",
        isOpen ? "Fechar menu" : "Abrir menu"
      );
      menuToggle.textContent = isOpen ? "✕" : "☰";
    });

    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        nav.classList.remove("open");
        menuToggle.setAttribute("aria-expanded", "false");
        menuToggle.setAttribute("aria-label", "Abrir menu");
        menuToggle.textContent = "☰";
      });
    });
  }

  // Formulário de atendimento pelo WhatsApp
  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();

      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }

      const nome = document.getElementById("nome").value.trim();
      const telefone = document.getElementById("telefone").value.trim();
      const regiao = document.getElementById("regiao").value.trim();
      const renda = document.getElementById("renda").value;
      const entrada = document.getElementById("entrada").value;
      const mcmv = document.getElementById("mcmv").value;
      const observacoes = document.getElementById("observacoes").value.trim();

      // Verifica se o telefone informado tem um formato razoável
      const digits = telefone.replace(/\D/g, "");

      if (digits.length < 10 || digits.length > 13) {
        formMessage.textContent =
          "Confira o WhatsApp informado. Digite o DDD e o número.";
        document.getElementById("telefone").focus();
        return;
      }

      const mensagem = [
        "Olá! Vim pelo site Empreendimentos Buenos SP e gostaria de conhecer opções de apartamentos na Grande São Paulo.",
        "",
        "Nome: " + nome,
        "Meu WhatsApp: " + telefone,
        "Cidade ou região: " + regiao,
        "Renda familiar: " + renda,
        "Entrada disponível: " + entrada,
        "Interesse no Minha Casa, Minha Vida: " + mcmv,
        "Observações: " + (observacoes || "Não informado")
      ].join("\n");

      const url =
        "https://wa.me/" +
        whatsappNumber +
        "?text=" +
        encodeURIComponent(mensagem);

      formMessage.textContent =
        "O WhatsApp será aberto. Confira a mensagem e toque em Enviar para iniciar o atendimento.";

      const whatsappWindow = window.open(url, "_blank");

      // Se o navegador bloquear a nova aba, oferece um link alternativo
      if (!whatsappWindow) {
        formMessage.innerHTML =
          'O navegador bloqueou a abertura automática. <a href="' +
          url +
          '" target="_blank" rel="noopener noreferrer">Clique aqui para abrir o WhatsApp</a>.';
      }
    });
  }
});
