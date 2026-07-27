(function () {
    "use strict";

    const page = document.querySelector("[data-crm-intelligence]");
    if (!page) return;

    const tabButtons = Array.from(page.querySelectorAll("[data-crm4-tab]"));
    const panels = Array.from(page.querySelectorAll("[data-crm4-panel]"));

    function activateSegment(segment, shouldScroll) {
        const selectedButton = tabButtons.find((button) => button.dataset.crm4Tab === segment);
        const selectedPanel = panels.find((panel) => panel.dataset.crm4Panel === segment);
        if (!selectedButton || !selectedPanel) return;

        tabButtons.forEach((button) => {
            const isActive = button === selectedButton;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", String(isActive));
        });
        panels.forEach((panel) => { panel.hidden = panel !== selectedPanel; });

        if (shouldScroll) {
            page.querySelector("[data-segments-section]")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => activateSegment(button.dataset.crm4Tab, false));
    });

    page.querySelectorAll("[data-open-segment]").forEach((button) => {
        button.addEventListener("click", () => activateSegment(button.dataset.openSegment, true));
    });

    page.querySelector("[data-scroll-campaign]")?.addEventListener("click", () => {
        page.querySelector("[data-campaign-section]")?.scrollIntoView({ behavior: "smooth", block: "start" });
        window.setTimeout(() => page.querySelector('input[name="nome"]')?.focus(), 450);
    });

    const settingsToggle = page.querySelector("[data-toggle-settings]");
    const settingsForm = page.querySelector("[data-settings-form]");
    settingsToggle?.addEventListener("click", () => {
        const expanded = settingsToggle.getAttribute("aria-expanded") === "true";
        settingsToggle.setAttribute("aria-expanded", String(!expanded));
        settingsToggle.textContent = expanded ? "⌄" : "⌃";
        settingsToggle.setAttribute("aria-label", expanded ? "Expandir configurações" : "Recolher configurações");
        settingsForm.hidden = expanded;
    });

    const messageField = page.querySelector('textarea[name="mensagem"]');
    const characterCount = page.querySelector("[data-character-count]");
    function updateCharacterCount() {
        if (!messageField || !characterCount) return;
        characterCount.textContent = `${messageField.value.length}/1000 caracteres`;
    }
    messageField?.addEventListener("input", updateCharacterCount);
    updateCharacterCount();

    page.querySelectorAll("[data-insert-variable]").forEach((button) => {
        button.addEventListener("click", () => {
            if (!messageField) return;
            const variable = button.dataset.insertVariable || "";
            const start = messageField.selectionStart ?? messageField.value.length;
            const end = messageField.selectionEnd ?? messageField.value.length;
            messageField.value = messageField.value.slice(0, start) + variable + messageField.value.slice(end);
            messageField.focus();
            messageField.setSelectionRange(start + variable.length, start + variable.length);
            updateCharacterCount();
        });
    });
})();
