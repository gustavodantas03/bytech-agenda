"use strict";
(() => {
  const page = document.querySelector("[data-status-url]");
  const button = document.getElementById("btnAtualizarStatus");
  if (!page) return;

  async function atualizarStatus(manual = false) {
    if (button && manual) { button.disabled = true; button.textContent = "Consultando..."; }
    try {
      const response = await fetch(page.dataset.statusUrl, {headers:{Accept:"application/json"}, credentials:"same-origin"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const text = document.getElementById("statusText");
      const dot = document.getElementById("statusDot");
      if (text) text.textContent = String(data.status || "desconectado").replaceAll("_", " ");
      if (dot) dot.classList.toggle("online", data.status === "conectado");
      const profile = document.getElementById("waProfile");
      const profileName = document.getElementById("waProfileName");
      const profileNumber = document.getElementById("waProfileNumber");
      const profilePhoto = document.getElementById("waProfilePhoto");
      const lastSync = document.getElementById("lastSyncText");
      if (profile) profile.hidden = data.status !== "conectado";
      if (profileName && data.nome) profileName.textContent = data.nome;
      if (profileNumber && data.numero) profileNumber.textContent = data.numero;
      if (profilePhoto && data.foto) profilePhoto.src = data.foto;
      if (lastSync && data.ultima_sincronizacao) lastSync.textContent = `Última sincronização: ${data.ultima_sincronizacao}`;
      if (!manual && data.status === "conectado" && document.querySelector(".wa-qr")) window.location.reload();
    } catch (error) { console.error("Falha ao consultar Evolution API:", error); }
    finally { if (button && manual) { button.disabled = false; button.textContent = "Atualizar status"; } }
  }
  if (button) button.addEventListener("click", () => atualizarStatus(true));
  atualizarStatus(false);
  window.setInterval(() => atualizarStatus(false), 8000);

  document.querySelectorAll(".wa-connect-tab").forEach((aba) => {
    aba.addEventListener("click", () => {
      document.querySelectorAll(".wa-connect-tab").forEach((a) => a.classList.remove("active"));
      document.querySelectorAll(".wa-connect-option").forEach((op) => { op.hidden = true; });
      aba.classList.add("active");
      const alvo = document.getElementById(aba.dataset.alvo);
      if (alvo) alvo.hidden = false;
    });
  });
})();
