const app = document.getElementById('app');
const modal = document.getElementById('modal');
const userSwitcher = document.getElementById('userSwitcher');

let currentUserId = Number(localStorage.getItem('userId') || 1);
let sessionUsers = [];

async function api(url, options = {}) {
  const headers = { 'Content-Type': 'application/json', 'X-User-Id': String(currentUserId), ...(options.headers || {}) };
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Erro inesperado' }));
    throw new Error(err.error || 'Erro');
  }
  if (res.status === 204) return null;
  return res.json();
}

function go(path) { history.pushState({}, '', path); render(); }
window.addEventListener('popstate', render);
document.body.addEventListener('click', (e) => {
  const link = e.target.closest('[data-link]');
  if (link) { e.preventDefault(); go(link.getAttribute('href')); }
});

function openModal(content) { modal.innerHTML = content; modal.showModal(); }
function closeModal() { modal.close(); }

async function loadSessionUsers() {
  sessionUsers = await fetch('/api/session/users').then(r => r.json());
  userSwitcher.innerHTML = sessionUsers.map(u => `<option value="${u.id}" ${u.id === currentUserId ? 'selected' : ''}>${u.nome}</option>`).join('');
  userSwitcher.onchange = () => {
    currentUserId = Number(userSwitcher.value);
    localStorage.setItem('userId', String(currentUserId));
    render();
  };
}

async function renderPlanejamentos() {
  app.innerHTML = '<div class="card">Carregando...</div>';
  const { items } = await api('/api/planejamentos?page=1&pageSize=50');
  app.innerHTML = `
    <div class="card"><div class="actions"><button class="primary" id="novoPlan">Novo Planejamento</button><button id="copiarPlan">Copiar de...</button></div></div>
    <table class="table"><thead><tr><th>Ano</th><th>Nome</th><th>Status</th><th>Atualizado em</th><th>Ações</th></tr></thead>
    <tbody>${items.length ? items.map(p => `<tr><td>${p.ano}</td><td>${p.nome}</td><td><span class="status ${p.status}">${p.status}</span></td><td>${new Date(p.atualizadoEm).toLocaleString('pt-BR')}</td><td><a href="/planejamentos/${p.id}" data-link>Abrir</a></td></tr>`).join('') : '<tr><td colspan="5">Nenhum planejamento.</td></tr>'}</tbody></table>
  `;

  document.getElementById('novoPlan').onclick = () => {
    openModal(`<form id="formNovo" class="grid"><h3>Novo Planejamento</h3><label>Nome <input name="nome" required></label><label>Ano <input name="ano" type="number" required></label><div class="actions"><button class="primary">Criar</button><button type="button" id="cancel">Cancelar</button></div><div class="error" id="err"></div></form>`);
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
    const src = await api('/api/planejamentos?page=1&pageSize=100');
    openModal(`<form id="formCopia" class="grid"><h3>Copiar estrutura</h3><label>Origem <select name="origem">${src.items.map(p => `<option value="${p.id}">${p.nome} (${p.ano})</option>`).join('')}</select></label><label>Novo nome <input name="nome" required></label><label>Novo ano <input type="number" name="ano" required></label><div class="actions"><button class="primary">Copiar</button><button type="button" id="cancel">Cancelar</button></div><div class="error" id="err"></div></form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('formCopia').onsubmit = async (e) => {
      e.preventDefault(); const fd = new FormData(e.target);
      try {
        await api(`/api/planejamentos/${fd.get('origem')}/copy`, { method: 'POST', body: JSON.stringify({ nome: fd.get('nome'), ano: Number(fd.get('ano')) }) });
        closeModal(); render();
      } catch (err) { document.getElementById('err').textContent = err.message; }
    };
  };
}

async function renderDetalhe(id) {
  app.innerHTML = '<div class="card">Carregando...</div>';
  const [plan, modelosRes] = await Promise.all([
    api(`/api/planejamentos/${id}`),
    api(`/api/planejamentos/${id}/modelos?page=1&pageSize=100`)
  ]);
  const items = modelosRes.items;
  app.innerHTML = `
    <section class="page-header"><div><h1 class="page-title">${plan.nome} (${plan.ano})</h1><div class="page-subtitle"><span class="status ${plan.status}">${plan.status}</span><span>Atualizado em ${new Date(plan.atualizadoEm).toLocaleString('pt-BR')}</span></div></div><div class="header-actions"><button class="primary" id="novoModelo">Novo Modelo</button></div></section>
    <section class="card"><table class="table"><thead><tr><th>Nome</th><th>Tipo</th><th>Atualizado</th><th>Ações</th></tr></thead><tbody>${items.length ? items.map(m => `<tr><td>${m.nome}</td><td>${m.tipo}</td><td>${new Date(m.atualizadoEm).toLocaleString('pt-BR')}</td><td class="actions"><a href="/planejamentos/${id}/modelos/${m.id}/editar" data-link>Editar Estrutura</a><a href="/planejamentos/${id}/modelos/${m.id}/preencher" data-link>Preencher</a><button data-del-modelo="${m.id}">Excluir</button></td></tr>`).join('') : '<tr><td colspan="4">Sem modelos.</td></tr>'}</tbody></table></section>
  `;
  document.getElementById('novoModelo').onclick = () => {
    openModal(`<form id="formModel" class="grid"><h3>Novo Modelo</h3><label>Nome <input name="nome" required></label><label>Tipo <select name="tipo"><option>receita</option><option>despesa</option><option>driver</option><option>outro</option></select></label><label>Descrição <textarea name="descricao"></textarea></label><div class="actions"><button class="primary">Salvar</button><button type="button" id="cancel">Cancelar</button></div><div class="error" id="err"></div></form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('formModel').onsubmit = async (e) => {
      e.preventDefault(); const fd = new FormData(e.target);
      try {
        await api(`/api/planejamentos/${id}/modelos`, { method: 'POST', body: JSON.stringify({ nome: fd.get('nome'), tipo: fd.get('tipo'), descricao: fd.get('descricao') }) });
        closeModal(); render();
      } catch (err) { document.getElementById('err').textContent = err.message; }
    };
  };
  app.querySelectorAll('[data-del-modelo]').forEach(btn => btn.onclick = async () => {
    if (!confirm('Excluir modelo?')) return;
    await api(`/api/modelos/${btn.dataset.delModelo}`, { method: 'DELETE' });
    render();
  });
}

async function renderEditor(planId, modeloId) {
  const [linhasRes, contas] = await Promise.all([api(`/api/modelos/${modeloId}/linhas?page=1&pageSize=200`), api('/api/contas-contabeis')]);
  const linhas = linhasRes.items;
  const contaLabel = Object.fromEntries(contas.map(c => [c.id, `${c.codigo} - ${c.nome}`]));
  app.innerHTML = `<div class="card"><h2>Editor de Estrutura</h2><a href="/planejamentos/${planId}" data-link>Voltar</a></div><div class="card"><button class="primary" id="addLinha">Adicionar Linha</button></div><table class="table"><thead><tr><th>Ordem</th><th>Nome</th><th>Tipo</th><th>Formato</th><th>Conta</th><th>Fórmula</th><th>Ações</th></tr></thead><tbody>${linhas.map((l, idx) => `<tr><td>${l.ordem}</td><td>${l.codigo} - ${l.nomeLinha}</td><td>${l.tipoLinha}</td><td>${l.formato}</td><td>${contaLabel[l.contaContabilId] || '-'}</td><td>${l.formula || ''}</td><td class="actions"><button data-move="up" data-id="${l.id}" ${idx===0?'disabled':''}>↑</button><button data-move="down" data-id="${l.id}" ${idx===linhas.length-1?'disabled':''}>↓</button><button data-edit="${l.id}">Editar</button><button data-del="${l.id}">Excluir</button></td></tr>`).join('')}</tbody></table>`;

  async function openLinhaForm(existing) {
    const defaultCode = `L${String(linhas.length + 1).padStart(3, '0')}`;
    openModal(`<form id="linhaForm" class="grid"><h3>${existing ? 'Editar' : 'Adicionar'} Linha</h3><label>Código <input name="codigo" value="${existing?.codigo || defaultCode}" required></label><label>Nome da linha <input name="nomeLinha" value="${existing?.nomeLinha || ''}" required></label><label>Tipo <select name="tipoLinha"><option ${existing?.tipoLinha==='input'?'selected':''}>input</option><option ${existing?.tipoLinha==='formula'?'selected':''}>formula</option><option ${existing?.tipoLinha==='header'?'selected':''}>header</option></select></label><label>Formato <select name="formato"><option ${existing?.formato==='moeda'?'selected':''}>moeda</option><option ${existing?.formato==='numero'?'selected':''}>numero</option><option ${existing?.formato==='percentual'?'selected':''}>percentual</option><option ${existing?.formato==='texto'?'selected':''}>texto</option></select></label><label>Conta contábil <select name="contaContabilId"><option value="">-</option>${contas.map(c=>`<option value="${c.id}" ${Number(existing?.contaContabilId)===c.id?'selected':''}>${c.codigo} - ${c.nome}</option>`).join('')}</select></label><label>Fórmula <input name="formula" value="${existing?.formula || ''}" placeholder="Ex.: L001 + L002"></label><div class="actions"><button class="primary">Salvar</button><button type="button" id="cancel">Cancelar</button></div><div id="err" class="error"></div></form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('linhaForm').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = { codigo: fd.get('codigo'), nomeLinha: fd.get('nomeLinha'), tipoLinha: fd.get('tipoLinha'), formato: fd.get('formato'), contaContabilId: fd.get('contaContabilId') || null, formula: fd.get('formula') || null };
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
  const [plan, ccs] = await Promise.all([api(`/api/planejamentos/${planId}`), api('/api/my-cost-centers')]);
  const ano = Number(plan.ano);
  let centroCustoId = ccs[0]?.id;

  async function draw() {
    if (!centroCustoId) {
      app.innerHTML = '<div class="card"><div class="state-box error">Você não possui Centro de Custo vinculado.</div></div>';
      return;
    }
    const [data, wf] = await Promise.all([
      api(`/api/modelos/${modeloId}/valores?centroCustoId=${centroCustoId}&ano=${ano}`),
      api(`/api/planejamentos/${planId}/workflow?centroCustoId=${centroCustoId}`)
    ]);
    const valMap = {}; data.valores.forEach(v => valMap[`${v.linhaId}-${v.mes}`] = v.valor);
    app.innerHTML = `<div class="card"><h2>Preenchimento Mensal</h2><a href="/planejamentos/${planId}" data-link>Voltar</a></div><div class="card"><label>Centro de Custo ativo<select id="ccSel">${ccs.map(c => `<option value="${c.id}" ${c.id===centroCustoId?'selected':''}>${c.nome}</option>`).join('')}</select></label><span class="status">Workflow: ${wf.status}</span></div><div class="card" style="overflow:auto"><table class="table"><thead><tr><th>Linha</th>${['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'].map(m=>`<th>${m}</th>`).join('')}<th>Total</th></tr></thead><tbody>${data.linhas.map(l => {
      const cls = l.tipoLinha === 'header' ? 'header-row' : '';
      const cells = Array.from({ length: 12 }, (_, i) => {
        const val = Number(valMap[`${l.id}-${i+1}`] ?? 0);
        return l.tipoLinha === 'input' ? `<td><input class="cell-input" data-linha="${l.id}" data-mes="${i+1}" value="${val}" ${wf.status!=='ABERTO'?'disabled':''}></td>` : `<td>${val.toFixed(2)}</td>`;
      }).join('');
      const total = Array.from({ length: 12 }, (_, i) => Number(valMap[`${l.id}-${i+1}`] ?? 0)).reduce((a,b)=>a+b,0);
      return `<tr class="${cls}"><td>${l.codigo} - ${l.nomeLinha}</td>${cells}<td>${total.toFixed(2)}</td></tr>`;
    }).join('')}</tbody></table></div>`;

    document.getElementById('ccSel').onchange = (e) => { centroCustoId = Number(e.target.value); draw(); };
    app.querySelectorAll('.cell-input').forEach(input => {
      input.onchange = async () => {
        await api(`/api/modelos/${modeloId}/valores/upsert`, { method: 'POST', body: JSON.stringify({ ano, centroCustoId, updates: [{ linhaId: Number(input.dataset.linha), mes: Number(input.dataset.mes), valor: Number(input.value || 0) }] }) });
        draw();
      };
    });
  }
  draw();
}

function renderParametrosShell() {
  app.innerHTML = `
    <section class="page-header"><div><h1 class="page-title">Parâmetros</h1><div class="page-subtitle">Gestão de usuários, cargos e escopo por Centro de Custo</div></div></section>
    <div id="paramContent"></div>`;
}

async function renderUsuarios() {
  renderParametrosShell();
  const [usersRes, ccsRes] = await Promise.all([
    api('/api/users?page=1&pageSize=200'),
    api('/api/cost-centers')
  ]);
  const items = usersRes.items;
  const allCCs = ccsRes.items;

  document.getElementById('paramContent').innerHTML = `<div class="card"><div class="table-toolbar"><input id="buscaUser" placeholder="Buscar usuários..."><div class="item-count">${items.length} usuários</div><button class="primary" id="novoUser">Novo usuário</button></div><table class="table"><thead><tr><th>Nome</th><th>Email/Login</th><th>Cargo</th><th>Status</th><th>Ações</th></tr></thead><tbody id="userRows"></tbody></table></div>`;

  const renderRows = (q='') => {
    const rows = items.filter(u => !q || `${u.nome} ${u.email}`.toLowerCase().includes(q.toLowerCase()));
    document.getElementById('userRows').innerHTML = rows.length ? rows.map(u => `<tr><td>${u.nome}</td><td>${u.email}</td><td>${u.role || '-'}</td><td>${u.status}</td><td class="actions">${u.status === 'ATIVO' ? `<button data-manage="${u.id}">Gerenciar</button>` : '<span class="muted">Sem ações</span>'}</td></tr>`).join('') : '<tr><td colspan="5">Sem usuários.</td></tr>';
    document.querySelectorAll('[data-manage]').forEach(btn => btn.onclick = () => openUserModal(items.find(u => u.id === Number(btn.dataset.manage))));
  };

  document.getElementById('buscaUser').oninput = (e) => renderRows(e.target.value);
  document.getElementById('novoUser').onclick = () => openUserModal();
  renderRows();

  function renderCcChecklist(selectedIds, role, filter='') {
    const blocked = role === 'DIRETORIA';
    const filtered = allCCs.filter(c => (`${c.code} ${c.name}`).toLowerCase().includes(filter.toLowerCase()));
    return `<div class="grid">${filtered.map(c => `<label><input type="checkbox" name="cc" value="${c.id}" ${selectedIds.includes(c.id)?'checked':''} ${blocked?'disabled':''}> ${c.code} - ${c.name}</label>`).join('')}</div>`;
  }

  function openUserModal(u) {
    const isEdit = !!u;
    let role = u?.role || 'OPERADOR';
    let selectedIds = [...(u?.costCenterIds || [])];
    const disabled = u?.status === 'INATIVO';

    const draw = (filter='') => {
      openModal(`<form id="fUser" class="grid"><h3>${isEdit ? 'Gerenciar usuário' : 'Novo usuário'}</h3>
        <label>Nome <input name="name" value="${u?.nome || ''}" ${disabled?'disabled':''} required></label>
        <label>Email/Login <input name="email" value="${u?.email || ''}" ${isEdit ? 'disabled' : ''} ${disabled?'disabled':''} required></label>
        <label>Cargo <select name="role" id="roleSel" ${disabled?'disabled':''}><option ${role==='OPERADOR'?'selected':''}>OPERADOR</option><option ${role==='GESTOR'?'selected':''}>GESTOR</option><option ${role==='DIRETORIA'?'selected':''}>DIRETORIA</option></select></label>
        <label>Buscar Centro de Custo <input id="ccSearch" value="${filter}" ${role==='DIRETORIA' || disabled ? 'disabled' : ''}></label>
        <div id="ccWrap">${renderCcChecklist(selectedIds, role, filter)}</div>
        ${role==='DIRETORIA' ? '<small>Diretoria possui acesso global; vínculos de CC serão ignorados.</small>' : ''}
        <div class="actions">
          ${isEdit && !disabled ? '<button type="button" class="destructive" id="inativarUser">Inativar usuário</button>' : ''}
          <button class="primary" ${disabled?'disabled':''}>Salvar</button>
          <button type="button" id="cancel">Fechar</button>
        </div><div id="err" class="error"></div></form>`);

      document.getElementById('cancel').onclick = closeModal;
      const roleSel = document.getElementById('roleSel');
      if (roleSel) roleSel.onchange = () => {
        role = roleSel.value;
        if (role === 'DIRETORIA') selectedIds = [];
        draw(document.getElementById('ccSearch')?.value || '');
      };
      const ccSearch = document.getElementById('ccSearch');
      if (ccSearch) ccSearch.oninput = () => draw(ccSearch.value);
      document.querySelectorAll('input[name="cc"]').forEach(chk => chk.onchange = () => {
        const id = Number(chk.value);
        if (chk.checked && !selectedIds.includes(id)) selectedIds.push(id);
        if (!chk.checked) selectedIds = selectedIds.filter(x => x !== id);
      });

      const inativar = document.getElementById('inativarUser');
      if (inativar) inativar.onclick = async () => {
        if (!confirm('Confirma inativação irreversível / sem reativação deste usuário?')) return;
        try {
          await api(`/api/users/${u.id}/inactivate`, { method: 'POST' });
          closeModal();
          renderUsuarios();
        } catch (err) { document.getElementById('err').textContent = err.message; }
      };

      document.getElementById('fUser').onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
          name: fd.get('name'),
          role,
          costCenterIds: role === 'DIRETORIA' ? [] : selectedIds
        };
        if (!isEdit) payload.email = fd.get('email');
        if (role !== 'DIRETORIA' && payload.costCenterIds.length === 0) {
          document.getElementById('err').textContent = 'Selecione ao menos 1 Centro de Custo para OPERADOR/GESTOR.';
          return;
        }
        try {
          if (isEdit) await api(`/api/users/${u.id}`, { method: 'PUT', body: JSON.stringify(payload) });
          else await api('/api/users', { method: 'POST', body: JSON.stringify(payload) });
          closeModal();
          renderUsuarios();
        } catch (err) { document.getElementById('err').textContent = err.message; }
      };
    };

    draw();
  }
}


async function renderAcessos() {
  const tab = renderParametrosShell(); if (tab !== 'acessos') return;
  const [roles, perms, rolePerms, users, userRoles] = await Promise.all([
    api('/api/parametros/roles'), api('/api/parametros/permissions'), api('/api/parametros/role-permissions'), api('/api/parametros/usuarios?page=1&pageSize=100').then(r=>r.items), api('/api/parametros/user-roles')
  ]);
  document.getElementById('paramContent').innerHTML = `
    <div class="card"><h3>User Roles</h3><div class="actions"><select id="urUser">${users.map(u=>`<option value="${u.id}">${u.nome}</option>`)}</select><select id="urRole">${roles.map(r=>`<option value="${r.id}">${r.name}</option>`)}</select><button class="primary" id="addUr">Vincular</button></div><table class="table"><thead><tr><th>Usuário</th><th>Role</th><th></th></tr></thead><tbody>${userRoles.map(ur=>`<tr><td>${ur.userNome}</td><td>${ur.roleName}</td><td><button class="destructive" data-del-ur='${JSON.stringify({userId:ur.userId,roleId:ur.roleId})}'>Remover</button></td></tr>`).join('')}</tbody></table></div>
    <div class="card"><h3>Role Permissions</h3><div class="actions"><select id="rpRole">${roles.map(r=>`<option value="${r.id}">${r.name}</option>`)}</select><select id="rpPerm">${perms.map(p=>`<option value="${p.id}">${p.key}</option>`)}</select><button class="primary" id="addRp">Vincular</button></div><table class="table"><thead><tr><th>Role</th><th>Permissão</th><th></th></tr></thead><tbody>${rolePerms.map(rp=>`<tr><td>${rp.roleName}</td><td>${rp.permissionKey}</td><td><button class="destructive" data-del-rp='${JSON.stringify({roleId:rp.roleId,permissionId:rp.permissionId})}'>Remover</button></td></tr>`).join('')}</tbody></table></div>
  `;
  document.getElementById('addUr').onclick = async () => { await api('/api/parametros/user-roles', { method:'POST', body: JSON.stringify({ userId:Number(document.getElementById('urUser').value), roleId:Number(document.getElementById('urRole').value) }) }); render(); };
  document.getElementById('addRp').onclick = async () => { await api('/api/parametros/role-permissions', { method:'POST', body: JSON.stringify({ roleId:Number(document.getElementById('rpRole').value), permissionId:Number(document.getElementById('rpPerm').value) }) }); render(); };
  document.querySelectorAll('[data-del-ur]').forEach(btn => btn.onclick = async () => { const p = JSON.parse(btn.dataset.delUr); await api('/api/parametros/user-roles', { method:'DELETE', body: JSON.stringify(p) }); render(); });
  document.querySelectorAll('[data-del-rp]').forEach(btn => btn.onclick = async () => { const p = JSON.parse(btn.dataset.delRp); await api('/api/parametros/role-permissions', { method:'DELETE', body: JSON.stringify(p) }); render(); });
}

async function renderCC() {
  const tab = renderParametrosShell(); if (tab !== 'cc') return;
  const { items } = await api('/api/centros-custo?page=1&pageSize=200');
  document.getElementById('paramContent').innerHTML = `<div class="card"><div class="actions"><button class="primary" id="novoCc">Novo CC</button></div><table class="table"><thead><tr><th>Nome</th><th>Ações</th></tr></thead><tbody>${items.map(c=>`<tr><td>${c.nome}</td><td class="actions"><button data-edit='${c.id}'>Editar</button><button class="destructive" data-del='${c.id}'>Excluir</button></td></tr>`).join('')}</tbody></table></div>`;
  document.getElementById('novoCc').onclick = () => openCcForm();
  document.querySelectorAll('[data-edit]').forEach(btn => btn.onclick = () => openCcForm(items.find(c => c.id===Number(btn.dataset.edit))));
  document.querySelectorAll('[data-del]').forEach(btn => btn.onclick = async () => { if(confirm('Excluir centro de custo?')) { await api(`/api/centros-custo/${btn.dataset.del}`, { method:'DELETE' }); render(); } });

  function openCcForm(cc){
    openModal(`<form id='fCc' class='grid'><h3>${cc?'Editar':'Novo'} CC</h3><label>Nome <input name='nome' value='${cc?.nome||''}' required></label><div class='actions'><button class='primary'>Salvar</button><button type='button' id='cancel'>Cancelar</button></div><div id='err' class='error'></div></form>`);
    document.getElementById('cancel').onclick = closeModal;
    document.getElementById('fCc').onsubmit = async (e) => { e.preventDefault(); const fd = new FormData(e.target); try { if (cc) await api(`/api/centros-custo/${cc.id}`, { method:'PUT', body: JSON.stringify({ nome: fd.get('nome') }) }); else await api('/api/centros-custo', { method:'POST', body: JSON.stringify({ nome: fd.get('nome') }) }); closeModal(); render(); } catch(err){ document.getElementById('err').textContent = err.message; } };
  }
}

async function renderVinculos() {
  const tab = renderParametrosShell(); if (tab !== 'vinculos') return;
  const [vinc, users, ccs] = await Promise.all([
    api('/api/parametros/user-cost-centers'), api('/api/parametros/usuarios?page=1&pageSize=100').then(r=>r.items), api('/api/centros-custo?page=1&pageSize=200').then(r=>r.items)
  ]);
  document.getElementById('paramContent').innerHTML = `<div class='card'><div class='actions'><select id='vUser'>${users.map(u=>`<option value='${u.id}'>${u.nome}</option>`)}</select><select id='vCc'>${ccs.map(c=>`<option value='${c.id}'>${c.nome}</option>`)}</select><select id='vType'><option>GESTOR_CC</option><option>OPERADOR_CC</option><option>LEITOR_CC</option></select><button class='primary' id='addV'>Vincular</button></div><table class='table'><thead><tr><th>Usuário</th><th>CC</th><th>Tipo</th><th></th></tr></thead><tbody>${vinc.map(v=>`<tr><td>${v.userNome}</td><td>${v.costCenterNome}</td><td>${v.linkType}</td><td><button class='destructive' data-del='${JSON.stringify({userId:v.userId,costCenterId:v.costCenterId})}'>Remover</button></td></tr>`).join('')}</tbody></table></div>`;
  document.getElementById('addV').onclick = async () => {
    await api('/api/parametros/user-cost-centers', { method:'POST', body: JSON.stringify({ userId:Number(document.getElementById('vUser').value), costCenterId:Number(document.getElementById('vCc').value), linkType: document.getElementById('vType').value }) });
    render();
  };
  document.querySelectorAll('[data-del]').forEach(btn => btn.onclick = async () => { const d = JSON.parse(btn.dataset.del); await api('/api/parametros/user-cost-centers', { method:'DELETE', body: JSON.stringify(d) }); render(); });
}

async function renderParametros() {
  return renderUsuarios();
}

async function render() {
  const path = location.pathname;
  document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
  const active = path.startsWith('/planejamentos') ? '/planejamentos' : (path.startsWith('/parametros') ? '/parametros' : '/planejamentos');
  document.querySelector(`.sidebar a[href="${active}"]`)?.classList.add('active');
  try {
    if (path === '/' || path === '/planejamentos') return renderPlanejamentos();
    if (path === '/parametros') return renderParametros();
    let m = path.match(/^\/planejamentos\/(\d+)$/); if (m) return renderDetalhe(m[1]);
    m = path.match(/^\/planejamentos\/(\d+)\/modelos\/(\d+)\/editar$/); if (m) return renderEditor(m[1], m[2]);
    m = path.match(/^\/planejamentos\/(\d+)\/modelos\/(\d+)\/preencher$/); if (m) return renderPreencher(m[1], m[2]);
    app.innerHTML = '<div class="card">Página não encontrada.</div>';
  } catch (err) {
    app.innerHTML = `<div class="card"><div class="state-box error">${err.message}</div></div>`;
  }
}

loadSessionUsers().then(render);
