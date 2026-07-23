export const config = window.APP_CONFIG || {};

export const rotulos = {
    profissionalSingular: config.profissionalSingular || "profissional",
    profissionalPlural: config.profissionalPlural || "profissionais",
    nomeEmpresa: config.nomeEmpresa || "empresa",
};

export function artigoProfissional() {
    return ["manicure", "depiladora"].includes(
        rotulos.profissionalSingular.toLowerCase()
    ) ? "uma" : "um";
}
