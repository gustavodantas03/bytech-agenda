"use strict";

(() => {
  const page = document.querySelector("[data-status-url]");
  const button = document.getElementById("btnAtualizarStatus");
  if (!page || !button) return;

  button.addEventListener("click", async () => {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Consultando...";

    try {
      const response = await fetch(page.dataset.statusUrl, {
        headers: { "Accept": "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const text = document.getElementById("statusText");
      const dot = document.getElementById("statusDot");
      if (!text || !dot) return;

      if (!data.configurado && data.status === "nao_configurado") {
        text.textContent = "Não configurado";
        dot.classList.remove("online");
        return;
      }

      text.textContent = String(data.status || "desconectado").replaceAll("_", " ");
      dot.classList.toggle("online", data.status === "conectado");
    } catch (error) {
      const text = document.getElementById("statusText");
      const dot = document.getElementById("statusDot");
      if (text) text.textContent = "Falha ao consultar";
      if (dot) dot.classList.remove("online");
      console.error("Falha ao consultar Evolution API:", error);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  });
})();
