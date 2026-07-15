document.addEventListener("DOMContentLoaded", () => {
    const elementos = document.querySelectorAll(
        ".reveal, .reveal-card"
    );

    const observador = new IntersectionObserver(
        (entradas) => {
            entradas.forEach((entrada) => {
                if (!entrada.isIntersecting) {
                    return;
                }

                entrada.target.classList.add("is-visible");
                observador.unobserve(entrada.target);
            });
        },
        {
            threshold: 0.12
        }
    );

    elementos.forEach((elemento) => {
        observador.observe(elemento);
    });

    const hero = document.querySelector(".landing-page .hero");
    const effects = hero?.querySelector(".hero-effects");

    if (
        hero &&
        effects &&
        window.matchMedia("(pointer: fine)").matches
    ) {
        hero.addEventListener("mousemove", (evento) => {
            const area = hero.getBoundingClientRect();

            const x =
                (evento.clientX - area.left) / area.width - 0.5;

            const y =
                (evento.clientY - area.top) / area.height - 0.5;

            effects.style.transform =
                `translate3d(${x * 22}px, ${y * 16}px, 0)`;
        });

        hero.addEventListener("mouseleave", () => {
            effects.style.transform =
                "translate3d(0, 0, 0)";
        });
    }
});