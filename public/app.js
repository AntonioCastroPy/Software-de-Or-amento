const app = document.getElementById('app');
const modal = document.getElementById('modal');

async function api(url, options = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Erro inesperado' }));
    throw new Error(err.error || 'Erro');
  }
  if (res.status === 204) return null;
  return res.json();
}

function go(path) {
  history.pushState({}, '', path);
  render();
}

document.body.addEventListener('click', (e) => {
  const link = e.target.closest('[data-link]');
  if (link) {
    e.preventDefault();
    go(link.getAttribute('href'));
  }
});

window.addEventListener('popstate', render);

function openModal(content) {
  modal.innerHTML = content;
  modal.showModal();
}

function closeModal() {
  modal.close();
}

async function renderPlanejamentos() {
  app.innerHTML = '<div class="card">Carregando...</div>';
  const { items } = await api('/api/planejamentos?page=1&pageSize=50');
  app.innerHTML = `
    <div class="card">
      <div class="actions">
        <button class="primary" id="novoPlan">Novo Planejamento</button>
        <button id="copiarPlan">Copiar de...</button>
      </div>
    </div>
    <table class="table">
      <thead><tr><th>Ano</th><th>Nome</th><th>Status</th><th>Atualizado em</th><th>Ações</th></tr></thead>
      <tbody>
      ${items.length ? items.map(p => `
        <tr>
          <td>${p.ano}</td><td>${p.nome}</td>
          <td><span class="status ${p.status}">${p.status}</span></td>
          <td>${new Date(p.atualizadoEm).toLocaleString('pt-BR')}</td>
          <td><a href="/planejamentos/${p.id}" data-link>Abrir</a></td>
        </tr>
      `).join('') : '<tr><td colspan="5">Nenhum planejamento.</td></tr>'}
      </tbody>
    </table>
  `;

  document.getElementById('novoPlan').onclick = () => {
    openModal(`
      <form method="dialog" id="formNovo" class="grid">
        <h3>Novo Planejamento</h3>
        <label>Nome <input name="nome" required></label>
        <label>Ano <input name="ano" type="number" required></label>
        <div class="actions"><button class="primary">Criar</button><button type="button" id="cancel">Cancelar</button></div>
        <div class="error" id="err"></div>
      </form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('formNovo').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api('/api/planejamentos', { method: 'POST', body: JSON.stringify({ nome: fd.get('nome'), ano: Number(fd.get('ano')) }) });
        closeModal(); render();
      } catch (err) { document.getElementById('err').textContent = err.message; }
    };
  };

  document.getElementById('copiarPlan').onclick = async () => {
    openModal('<div class="card">Carregando...</div>');
    const src = await api('/api/planejamentos?page=1&pageSize=100');
    openModal(`
      <form method="dialog" id="formCopia" class="grid">
        <h3>Copiar estrutura</h3>
        <label>Origem <select name="origem">${src.items.map(p => `<option value="${p.id}">${p.nome} (${p.ano})</option>`).join('')}</select></label>
        <label>Novo nome <input name="nome" required></label>
        <label>Novo ano <input type="number" name="ano" required></label>
        <div class="small">Copia modelos e linhas. Não copia valores.</div>
        <div class="actions"><button class="primary">Copiar</button><button type="button" id="cancel">Cancelar</button></div>
        <div class="error" id="err"></div>
      </form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('formCopia').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api(`/api/planejamentos/${fd.get('origem')}/copy`, { method: 'POST', body: JSON.stringify({ nome: fd.get('nome'), ano: Number(fd.get('ano')) }) });
        closeModal(); render();
      } catch (err) { document.getElementById('err').textContent = err.message; }
    };
  };
}

async function renderDetalhe(id) {
  app.innerHTML = '<div class="card"><div class="state-box">Carregando modelos...</div></div>';

  let plan;
  try {
    plan = await api(`/api/planejamentos/${id}`);
  } catch (err) {
    app.innerHTML = `<div class="card"><div class="state-box error">Erro ao carregar planejamento: ${err.message}</div></div>`;
    return;
  }

  const state = { items: [], q: '', tipo: '' };

  function filteredItems() {
    return state.items.filter((m) => {
      const passName = !state.q || m.nome.toLowerCase().includes(state.q.toLowerCase());
      const passTipo = !state.tipo || m.tipo === state.tipo;
      return passName && passTipo;
    });
  }

  function renderTable(errorMsg = null) {
    const items = filteredItems();
    const countLabel = `${items.length} ${items.length === 1 ? 'modelo' : 'modelos'}`;
    app.innerHTML = `
      <section class="page-header">
        <div>
          <h1 class="page-title">${plan.nome} (${plan.ano})</h1>
          <div class="page-subtitle">
            <span class="status ${plan.status}">${plan.status}</span>
            <span>Atualizado em ${new Date(plan.atualizadoEm).toLocaleString('pt-BR')}</span>
          </div>
        </div>
        <div class="header-actions">
          <button class="primary" id="novoModelo">Novo Modelo</button>
          <div class="dropdown">
            <button id="globalMenuBtn" aria-label="Mais ações">...</button>
            <div class="menu" id="globalMenu">
              <button type="button">Copiar Estrutura (placeholder)</button>
              <button type="button">Configurações (placeholder)</button>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="table-toolbar">
          <input id="searchModelo" placeholder="Buscar modelos..." value="${state.q}">
          <select id="tipoModelo">
            <option value="">Todos os tipos</option>
            <option value="receita" ${state.tipo === 'receita' ? 'selected' : ''}>receita</option>
            <option value="despesa" ${state.tipo === 'despesa' ? 'selected' : ''}>despesa</option>
            <option value="driver" ${state.tipo === 'driver' ? 'selected' : ''}>driver</option>
            <option value="outro" ${state.tipo === 'outro' ? 'selected' : ''}>outro</option>
          </select>
          <div class="item-count">${countLabel}</div>
        </div>

        ${errorMsg ? `<div class="state-box error">${errorMsg}</div>` : ''}
        ${!errorMsg && items.length === 0 ? '<div class="state-box">Nenhum modelo encontrado para os filtros aplicados.</div>' : ''}

        ${!errorMsg && items.length ? `
          <table class="table">
            <thead><tr><th>Nome</th><th>Tipo</th><th>Atualizado</th><th style="width:220px">Ações</th></tr></thead>
            <tbody>
              ${items.map(m => `
                <tr>
                  <td>
                    <div class="model-name">${m.nome}</div>
                    <div class="muted">${m.descricao || 'Sem descrição'}</div>
                  </td>
                  <td><span class="muted">${m.tipo}</span></td>
                  <td><span class="muted">${new Date(m.atualizadoEm).toLocaleString('pt-BR')}</span></td>
                  <td>
                    <div class="actions">
                      <a href="/planejamentos/${id}/modelos/${m.id}/preencher" data-link><button class="primary small">Preencher</button></a>
                      <div class="dropdown">
                        <button class="small" data-row-menu="${m.id}">...</button>
                        <div class="menu" id="rowMenu-${m.id}">
                          <a href="/planejamentos/${id}/modelos/${m.id}/editar" data-link>Editar estrutura</a>
                          <button type="button" data-dup-modelo="${m.id}">Duplicar (placeholder)</button>
                          <button type="button" class="danger-item" data-del-modelo="${m.id}">Excluir</button>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        ` : ''}
      </section>
    `;

    const globalBtn = document.getElementById('globalMenuBtn');
    const globalMenu = document.getElementById('globalMenu');
    globalBtn.onclick = (e) => {
      e.stopPropagation();
      globalMenu.classList.toggle('open');
    };

    document.getElementById('searchModelo').oninput = (e) => {
      state.q = e.target.value;
      renderTable(errorMsg);
    };
    document.getElementById('tipoModelo').onchange = (e) => {
      state.tipo = e.target.value;
      renderTable(errorMsg);
    };

    app.querySelectorAll('[data-row-menu]').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        document.querySelectorAll('.menu.open').forEach(menu => menu.classList.remove('open'));
        const menu = document.getElementById(`rowMenu-${btn.dataset.rowMenu}`);
        menu.classList.toggle('open');
      };
    });

    app.querySelectorAll('[data-dup-modelo]').forEach(btn => btn.onclick = () => alert('Duplicar modelo (placeholder nesta fase).'));
    app.querySelectorAll('[data-del-modelo]').forEach(btn => btn.onclick = async () => {
      const ok = confirm('Tem certeza que deseja excluir este modelo?');
      if (!ok) return;
      try {
        await api(`/api/modelos/${btn.dataset.delModelo}`, { method: 'DELETE' });
        await loadModelos();
      } catch (err) {
        renderTable(err.message);
      }
    });

    document.addEventListener('click', () => document.querySelectorAll('.menu.open').forEach(menu => menu.classList.remove('open')), { once: true });

    document.getElementById('novoModelo').onclick = () => {
      openModal(`
        <form id="formModel" class="grid" method="dialog">
          <h3>Novo Modelo</h3>
          <label>Nome <input name="nome" required></label>
          <label>Tipo <select name="tipo"><option>receita</option><option>despesa</option><option>driver</option><option>outro</option></select></label>
          <label>Descrição <textarea name="descricao"></textarea></label>
          <div class="actions"><button class="primary">Salvar</button><button type="button" id="cancel">Cancelar</button></div><div class="error" id="err"></div>
        </form>
      `);
      document.getElementById('cancel').onclick = closeModal;
      document.getElementById('formModel').onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          await api(`/api/planejamentos/${id}/modelos`, { method: 'POST', body: JSON.stringify({ nome: fd.get('nome'), tipo: fd.get('tipo'), descricao: fd.get('descricao') }) });
          closeModal();
          await loadModelos();
        } catch (err) { document.getElementById('err').textContent = err.message; }
      };
    };
  }

  async function loadModelos() {
    app.innerHTML = `
      <section class="page-header">
        <div>
          <h1 class="page-title">${plan.nome} (${plan.ano})</h1>
          <div class="page-subtitle"><span class="status ${plan.status}">${plan.status}</span><span>Atualizado em ${new Date(plan.atualizadoEm).toLocaleString('pt-BR')}</span></div>
        </div>
      </section>
      <section class="card"><div class="state-box">Carregando modelos...</div></section>
    `;
    try {
      const { items } = await api(`/api/planejamentos/${id}/modelos?page=1&pageSize=100`);
      state.items = items;
      renderTable();
    } catch (err) {
      renderTable(`Erro ao carregar modelos: ${err.message}`);
    }
  }

  await loadModelos();
}


async function renderEditor(planId, modeloId) {
  const [linhasRes, contas] = await Promise.all([
    api(`/api/modelos/${modeloId}/linhas?page=1&pageSize=200`),
    api('/api/contas-contabeis')
  ]);
  const linhas = linhasRes.items;
  const contaLabel = Object.fromEntries(contas.map(c => [c.id, `${c.codigo} - ${c.nome}`]));
  app.innerHTML = `
    <div class="card"><h2>Editor de Estrutura</h2><a href="/planejamentos/${planId}" data-link>Voltar</a></div>
    <div class="card"><button class="primary" id="addLinha">Adicionar Linha</button></div>
    <table class="table"><thead><tr><th>Ordem</th><th>Nome</th><th>Tipo</th><th>Formato</th><th>Conta</th><th>Fórmula</th><th>Ações</th></tr></thead>
    <tbody>${linhas.map((l, idx) => `<tr>
      <td>${l.ordem}</td><td>${l.codigo} - ${l.nomeLinha}</td><td>${l.tipoLinha}</td><td>${l.formato}</td><td>${contaLabel[l.contaContabilId] || '-'}</td><td>${l.formula || ''}</td>
      <td class="actions">
        <button data-move="up" data-id="${l.id}" ${idx===0?'disabled':''}>↑</button>
        <button data-move="down" data-id="${l.id}" ${idx===linhas.length-1?'disabled':''}>↓</button>
        <button data-edit="${l.id}">Editar</button>
        <button data-del="${l.id}">Excluir</button>
      </td>
    </tr>`).join('')}</tbody></table>
  `;

  async function openLinhaForm(existing) {
    const defaultCode = `L${String(linhas.length + 1).padStart(3, '0')}`;
    openModal(`
      <form id="linhaForm" class="grid" method="dialog">
        <h3>${existing ? 'Editar' : 'Adicionar'} Linha</h3>
        <label>Código <input name="codigo" value="${existing?.codigo || defaultCode}" required></label>
        <label>Nome da linha <input name="nomeLinha" value="${existing?.nomeLinha || ''}" required></label>
        <label>Tipo <select name="tipoLinha"><option ${existing?.tipoLinha==='input'?'selected':''}>input</option><option ${existing?.tipoLinha==='formula'?'selected':''}>formula</option><option ${existing?.tipoLinha==='header'?'selected':''}>header</option></select></label>
        <label>Formato <select name="formato"><option ${existing?.formato==='moeda'?'selected':''}>moeda</option><option ${existing?.formato==='numero'?'selected':''}>numero</option><option ${existing?.formato==='percentual'?'selected':''}>percentual</option><option ${existing?.formato==='texto'?'selected':''}>texto</option></select></label>
        <label>Conta contábil <select name="contaContabilId"><option value="">-</option>${contas.map(c=>`<option value="${c.id}" ${Number(existing?.contaContabilId)===c.id?'selected':''}>${c.codigo} - ${c.nome}</option>`).join('')}</select></label>
        <label>Fórmula <input name="formula" value="${existing?.formula || ''}" placeholder="Ex.: L001 + L002"></label>
        <div class="small">Referências por código (L001). Operadores + - * /, parênteses e SOMA(...) / SOMAR(...)</div>
        <div class="actions"><button class="primary">Salvar</button><button type="button" id="cancel">Cancelar</button></div><div id="err" class="error"></div>
      </form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('linhaForm').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {
        codigo: fd.get('codigo'), nomeLinha: fd.get('nomeLinha'), tipoLinha: fd.get('tipoLinha'), formato: fd.get('formato'),
        contaContabilId: fd.get('contaContabilId') || null, formula: fd.get('formula') || null
      };
      try {
        if (existing) await api(`/api/linhas/${existing.id}`, { method: 'PUT', body: JSON.stringify(payload) });
        else await api(`/api/modelos/${modeloId}/linhas`, { method: 'POST', body: JSON.stringify(payload) });
        closeModal(); render();
      } catch (err) { document.getElementById('err').textContent = err.message; }
    };
  }

  document.getElementById('addLinha').onclick = () => openLinhaForm();
  app.querySelectorAll('[data-edit]').forEach(btn => btn.onclick = () => openLinhaForm(linhas.find(x => x.id === Number(btn.dataset.edit))));
  app.querySelectorAll('[data-del]').forEach(btn => btn.onclick = async () => { await api(`/api/linhas/${btn.dataset.del}`, { method: 'DELETE' }); render(); });
  app.querySelectorAll('[data-move]').forEach(btn => btn.onclick = async () => {
    const id = Number(btn.dataset.id);
    const idx = linhas.findIndex(l => l.id === id);
    const swapIdx = btn.dataset.move === 'up' ? idx - 1 : idx + 1;
    [linhas[idx], linhas[swapIdx]] = [linhas[swapIdx], linhas[idx]];
    await api(`/api/modelos/${modeloId}/linhas/reorder`, { method: 'POST', body: JSON.stringify({ orderedIds: linhas.map(l => l.id) }) });
    render();
  });
}

async function renderPreencher(planId, modeloId) {
  const [plan, ccs, linhasRes] = await Promise.all([
    api(`/api/planejamentos/${planId}`),
    api('/api/centros-custo'),
    api(`/api/modelos/${modeloId}/linhas?page=1&pageSize=200`)
  ]);
  const ano = Number(plan.ano);
  let centroCustoId = ccs[0]?.id;

  async function draw() {
    const data = await api(`/api/modelos/${modeloId}/valores?centroCustoId=${centroCustoId}&ano=${ano}`);
    const valMap = {};
    data.valores.forEach(v => valMap[`${v.linhaId}-${v.mes}`] = v.valor);

    app.innerHTML = `
      <div class="card"><h2>Preenchimento Mensal</h2><a href="/planejamentos/${planId}" data-link>Voltar</a></div>
      <div class="card"><label>Centro de Custo
        <select id="ccSel">${ccs.map(c => `<option value="${c.id}" ${c.id===centroCustoId?'selected':''}>${c.nome}</option>`).join('')}</select>
      </label></div>
      <div class="card" style="overflow:auto">
      <table class="table" id="sheet"><thead><tr><th>Linha</th>${['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'].map(m=>`<th>${m}</th>`).join('')}<th>Total</th></tr></thead>
      <tbody>
      ${data.linhas.map(l => {
        const cls = l.tipoLinha === 'header' ? 'header-row' : '';
        const cells = Array.from({ length: 12 }, (_, i) => {
          const val = Number(valMap[`${l.id}-${i+1}`] ?? 0);
          if (l.tipoLinha === 'input') return `<td><input class="cell-input" data-linha="${l.id}" data-mes="${i+1}" value="${val}"></td>`;
          return `<td>${val.toFixed(2)}</td>`;
        }).join('');
        const total = Array.from({ length: 12 }, (_, i) => Number(valMap[`${l.id}-${i+1}`] ?? 0)).reduce((a,b)=>a+b,0);
        return `<tr class="${cls}"><td>${l.codigo} - ${l.nomeLinha}</td>${cells}<td>${total.toFixed(2)}</td></tr>`;
      }).join('')}
      </tbody></table></div>
    `;

    document.getElementById('ccSel').onchange = (e) => { centroCustoId = Number(e.target.value); draw(); };

    app.querySelectorAll('.cell-input').forEach(input => {
      input.onchange = async () => {
        await api(`/api/modelos/${modeloId}/valores/upsert`, { method: 'POST', body: JSON.stringify({ ano, centroCustoId, updates: [{ linhaId: Number(input.dataset.linha), mes: Number(input.dataset.mes), valor: Number(input.value || 0) }] }) });
        draw();
      };

      input.oncontextmenu = (e) => {
        e.preventDefault();
        document.querySelector('.context-menu')?.remove();
        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.style.left = `${e.clientX}px`;
        menu.style.top = `${e.clientY}px`;
        menu.innerHTML = '<button id="replicar">Replicar para os meses à frente</button>';
        document.body.appendChild(menu);
        document.getElementById('replicar').onclick = () => {
          menu.remove();
          openModal(`
            <form id="replicaForm" class="grid" method="dialog">
              <h3>Replicar valor</h3>
              <label>Mês final <select name="mesFinal">${Array.from({length:12},(_,i)=>`<option value="${i+1}" ${i===11?'selected':''}>${i+1}</option>`)}</select></label>
              <label><input type="checkbox" checked disabled> Replicar apenas valor</label>
              <div class="actions"><button class="primary">Aplicar</button><button type="button" id="cancel">Cancelar</button></div>
            </form>
          `);
          document.getElementById('cancel').onclick = closeModal;
          document.getElementById('replicaForm').onsubmit = async (ev) => {
            ev.preventDefault();
            const fd = new FormData(ev.target);
            const mesAtual = Number(input.dataset.mes);
            const mesFinal = Number(fd.get('mesFinal'));
            const ups = [];
            for (let m = mesAtual + 1; m <= mesFinal; m++) ups.push({ linhaId: Number(input.dataset.linha), mes: m, valor: Number(input.value || 0) });
            if (ups.length) await api(`/api/modelos/${modeloId}/valores/upsert`, { method: 'POST', body: JSON.stringify({ ano, centroCustoId, updates: ups }) });
            closeModal(); draw();
          };
        };
        document.addEventListener('click', () => menu.remove(), { once: true });
      };
    });
  }
  draw();
}

function renderParametros() {
  app.innerHTML = '<div class="card"><h2>Parâmetros</h2><p>Placeholder nesta entrega. Cadastros serão implementados depois.</p></div>';
}

async function render() {
  const path = location.pathname;
  document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
  const active = path.startsWith('/planejamentos') ? '/planejamentos' : (path.startsWith('/parametros') ? '/parametros' : '/planejamentos');
  document.querySelector(`.sidebar a[href="${active}"]`)?.classList.add('active');
  try {
    if (path === '/' || path === '/planejamentos') return renderPlanejamentos();
    if (path === '/parametros') return renderParametros();
    let m = path.match(/^\/planejamentos\/(\d+)$/);
    if (m) return renderDetalhe(m[1]);
    m = path.match(/^\/planejamentos\/(\d+)\/modelos\/(\d+)\/editar$/);
    if (m) return renderEditor(m[1], m[2]);
    m = path.match(/^\/planejamentos\/(\d+)\/modelos\/(\d+)\/preencher$/);
    if (m) return renderPreencher(m[1], m[2]);
    app.innerHTML = '<div class="card">Página não encontrada.</div>';
  } catch (err) {
    app.innerHTML = `<div class="card">Erro: ${err.message}</div>`;
  }
}

render();
