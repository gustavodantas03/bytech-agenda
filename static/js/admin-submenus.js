document.addEventListener('DOMContentLoaded', function () {
    const nav = document.querySelector('.admin-sidebar .admin-nav');
    if (!nav || nav.dataset.submenusReady) return;

    nav.dataset.submenusReady = '1';

    const grupos = [
        { nome: 'Agendamentos', icone: '◷',
          itens: ['Agenda'] },
        { nome: 'Clientes e CRM', icone: '♟',
          itens: ['CRM', 'Fidelidade', 'Clientes'] },
        { nome: 'Serviços', icone: '✦',
          itens: ['Serviços', 'Profissionais', 'Manicures'],
          rotas: ['/funcionarios'] },
        { nome: 'Vendas e estoque', icone: '▣',
          itens: ['Produtos', 'PDV / Vendas'] },
        { nome: 'Comunicação', icone: '◉',
          itens: ['Comunicação'] },
        { nome: 'Gestão', icone: '▤',
          itens: ['Relatórios', 'Equipe'] },
        { nome: 'Configurações', icone: '◈',
          itens: ['Meu espaço', 'Minha empresa', 'Minha conta', 'Personalização da página pública'] }
    ];

    function normalizar(valor) {
        return (valor || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .trim()
            .toLowerCase();
    }

    const elementos = Array.from(nav.children);

    grupos.forEach(function (grupo) {
        const selecionados = elementos.filter(function (elemento) {
            if (!elemento.isConnected) return false;

            if (elemento.tagName === 'DETAILS') {
                const titulo = elemento.querySelector(
                    'summary > span:nth-child(2)'
                );
                return titulo &&
                    normalizar(titulo.textContent) === normalizar(grupo.nome);
            }

            const rotulo = elemento.querySelector(
                '.admin-nav-link > span:last-child'
            );

            const nome = rotulo
                ? normalizar(rotulo.textContent)
                : normalizar(elemento.textContent);

            const correspondeNome = grupo.itens.some(function (item) {
                return nome === normalizar(item);
            });

            const link = elemento.getAttribute('href') || '';
            const correspondeRota = (grupo.rotas || []).some(function (rota) {
                return link.includes(rota);
            });

            return correspondeNome || correspondeRota;
        });

        if (!selecionados.length) return;

        const detalhes = document.createElement('details');
        detalhes.className = 'admin-nav-group';

        const resumo = document.createElement('summary');
        resumo.className = 'admin-nav-link admin-nav-group-toggle';

        const icone = document.createElement('span');
        icone.className = 'admin-nav-icon';
        icone.textContent = grupo.icone;

        const titulo = document.createElement('span');
        titulo.textContent = grupo.nome;

        const seta = document.createElement('span');
        seta.className = 'admin-nav-chevron';
        seta.textContent = '⌄';

        resumo.append(icone, titulo, seta);

        const submenu = document.createElement('div');
        submenu.className = 'admin-nav-submenu';

        selecionados.forEach(function (elemento) {
            if (elemento.tagName === 'DETAILS') {
                elemento.querySelectorAll('a.admin-nav-sublink')
                    .forEach(function (link) {
                        submenu.appendChild(link);
                    });
                elemento.remove();
            } else {
                elemento.classList.remove('admin-nav-link');
                elemento.classList.add('admin-nav-sublink');
                submenu.appendChild(elemento);
            }
        });

        if (grupo.nome === 'Serviços') {
            const links = Array.from(submenu.children);
            const servicos = links.find(function (link) {
                return (link.getAttribute('href') || '').includes('/servicos');
            });
            if (servicos) {
                submenu.prepend(servicos);
            }
        }

        detalhes.append(resumo, submenu);

        if (submenu.querySelector('.active')) {
            detalhes.open = true;
        }

        nav.appendChild(detalhes);
    });

    nav.querySelectorAll('details.admin-nav-group')
        .forEach(function (grupo) {
            grupo.addEventListener('toggle', function () {
                if (!grupo.open) return;

                nav.querySelectorAll('details.admin-nav-group')
                    .forEach(function (outro) {
                        if (outro !== grupo) outro.open = false;
                    });
            });
        });
});

/* Acabamento visual do menu */
document.addEventListener('DOMContentLoaded', function () {
    const nav = document.querySelector('.admin-sidebar .admin-nav');
    if (!nav) return;

    const icones = {
        'Agendamentos': 'calendar-days',
        'Clientes e CRM': 'users',
        'Serviços': 'scissors',
        'Vendas e estoque': 'shopping-bag',
        'Comunicação': 'message-circle',
        'Gestão': 'chart-column',
        'Configurações': 'settings'
    };

    const caminhos = {
        'calendar-days': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
        'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
        'scissors': '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="m8.12 8.12 12.76 12.76M14.8 9.2l6.08-6.08M8.12 15.88l3.6-3.6"/>',
        'shopping-bag': '<path d="M6 7h12l1 14H5L6 7Z"/><path d="M9 9V6a3 3 0 0 1 6 0v3"/>',
        'message-circle': '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8A8.5 8.5 0 0 1 12.5 20a8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8A8.5 8.5 0 0 1 12.5 3H13a8.48 8.48 0 0 1 8 8v.5Z"/>',
        'chart-column': '<path d="M3 3v18h18M7 16v-4M12 16V8M17 16V5"/>',
        'settings': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06-2 2-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21h-3v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06-2-2 .06-.06A1.65 1.65 0 0 0 7.4 15a1.65 1.65 0 0 0-1.51-1H5v-3h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06 2-2 .06.06A1.65 1.65 0 0 0 10 6.6a1.65 1.65 0 0 0 1-1.51V5h3v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06 2 2-.06.06A1.65 1.65 0 0 0 18.6 10a1.65 1.65 0 0 0 1.51 1H21v3h-.09A1.65 1.65 0 0 0 19.4 15Z"/>'
    };

    nav.querySelectorAll('.admin-nav-group').forEach(function (grupo) {
        const titulo = grupo.querySelector('.admin-nav-group-toggle > span:nth-child(2)');
        const icone = grupo.querySelector('.admin-nav-group-toggle .admin-nav-icon');

        if (!titulo || !icone) return;

        const nome = titulo.textContent.trim();
        const tipo = icones[nome];

        if (!tipo || !caminhos[tipo]) return;

        icone.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + caminhos[tipo] + '</svg>';
    });
});
