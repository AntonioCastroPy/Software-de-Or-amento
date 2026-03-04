import json
import re
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
DB_PATH = ROOT / "data.sqlite"


def now():
    return datetime.utcnow().isoformat()


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def ensure_valores_schema(conn):
    columns = {row['name'] for row in conn.execute("PRAGMA table_info(valores_mensais)").fetchall()}
    if 'ano' in columns:
        return
    conn.executescript(
        """
        ALTER TABLE valores_mensais RENAME TO valores_mensais_old;
        CREATE TABLE valores_mensais (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          linhaId INTEGER NOT NULL,
          centroCustoId INTEGER NOT NULL,
          ano INTEGER NOT NULL,
          mes INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
          valor REAL NOT NULL DEFAULT 0,
          origem TEXT NOT NULL CHECK(origem IN ('manual','calculado')),
          atualizadoEm TEXT NOT NULL,
          FOREIGN KEY(linhaId) REFERENCES linhas_modelo(id) ON DELETE CASCADE,
          FOREIGN KEY(centroCustoId) REFERENCES centros_custo(id) ON DELETE CASCADE,
          UNIQUE(linhaId, centroCustoId, ano, mes)
        );
        INSERT INTO valores_mensais (linhaId, centroCustoId, ano, mes, valor, origem, atualizadoEm)
        SELECT vm.linhaId, vm.centroCustoId, p.ano, vm.mes, vm.valor, vm.origem, vm.atualizadoEm
          FROM valores_mensais_old vm
          JOIN linhas_modelo l ON l.id = vm.linhaId
          JOIN modelos m ON m.id = l.modeloId
          JOIN planejamentos p ON p.id = m.planejamentoId;
        DROP TABLE valores_mensais_old;
        """
    )


def init_db():
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planejamentos (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              nome TEXT NOT NULL,
              ano INTEGER NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('draft','aberto','fechado')) DEFAULT 'draft',
              criadoEm TEXT NOT NULL,
              atualizadoEm TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS modelos (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              planejamentoId INTEGER NOT NULL,
              nome TEXT NOT NULL,
              tipo TEXT NOT NULL CHECK(tipo IN ('receita','despesa','driver','outro')),
              descricao TEXT,
              ordem INTEGER NOT NULL,
              criadoEm TEXT NOT NULL,
              atualizadoEm TEXT NOT NULL,
              FOREIGN KEY(planejamentoId) REFERENCES planejamentos(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS linhas_modelo (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              modeloId INTEGER NOT NULL,
              codigo TEXT NOT NULL,
              nomeLinha TEXT NOT NULL,
              tipoLinha TEXT NOT NULL CHECK(tipoLinha IN ('input','formula','header')),
              formato TEXT NOT NULL CHECK(formato IN ('moeda','numero','percentual','texto')),
              formula TEXT,
              referencia TEXT,
              contaContabilId INTEGER,
              ordem INTEGER NOT NULL,
              criadoEm TEXT NOT NULL,
              atualizadoEm TEXT NOT NULL,
              FOREIGN KEY(modeloId) REFERENCES modelos(id) ON DELETE CASCADE,
              UNIQUE(modeloId,codigo)
            );
            CREATE TABLE IF NOT EXISTS centros_custo (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS contas_contabeis (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE NOT NULL, nome TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS valores_mensais (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              linhaId INTEGER NOT NULL,
              centroCustoId INTEGER NOT NULL,
              ano INTEGER NOT NULL,
              mes INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
              valor REAL NOT NULL DEFAULT 0,
              origem TEXT NOT NULL CHECK(origem IN ('manual','calculado')),
              atualizadoEm TEXT NOT NULL,
              FOREIGN KEY(linhaId) REFERENCES linhas_modelo(id) ON DELETE CASCADE,
              FOREIGN KEY(centroCustoId) REFERENCES centros_custo(id) ON DELETE CASCADE,
              UNIQUE(linhaId, centroCustoId, ano, mes)
            );

            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              nome TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS roles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS permissions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              key TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS role_permissions (
              roleId INTEGER NOT NULL,
              permissionId INTEGER NOT NULL,
              PRIMARY KEY(roleId, permissionId),
              FOREIGN KEY(roleId) REFERENCES roles(id) ON DELETE CASCADE,
              FOREIGN KEY(permissionId) REFERENCES permissions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS user_roles (
              userId INTEGER NOT NULL,
              roleId INTEGER NOT NULL,
              PRIMARY KEY(userId, roleId),
              FOREIGN KEY(userId) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(roleId) REFERENCES roles(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS user_cost_centers (
              userId INTEGER NOT NULL,
              costCenterId INTEGER NOT NULL,
              linkType TEXT NOT NULL CHECK(linkType IN ('GESTOR','OPERADOR')),
              PRIMARY KEY(userId, costCenterId),
              FOREIGN KEY(userId) REFERENCES users(id) ON DELETE CASCADE,
              FOREIGN KEY(costCenterId) REFERENCES centros_custo(id) ON DELETE CASCADE
            );
            """
        )
        ensure_valores_schema(conn)
        seed_data(conn)


def seed_data(conn):
    if conn.execute('SELECT COUNT(*) c FROM centros_custo').fetchone()['c'] == 0:
        conn.executemany('INSERT INTO centros_custo(nome) VALUES(?)', [
            ('Administração',), ('Armazém',), ('Comercial',), ('Grãos',), ('Insumos',), ('Logística',)
        ])
    if conn.execute('SELECT COUNT(*) c FROM contas_contabeis').fetchone()['c'] == 0:
        contas = [
            ('1.1.01', 'Caixa'), ('1.1.02', 'Bancos'), ('2.1.01', 'Fornecedores'),
            ('3.1.01', 'Receita Venda Milho'), ('3.1.02', 'Receita Venda Soja'),
            ('4.1.01', 'Despesa Administrativa'), ('4.1.02', 'Despesa Logística'), ('4.1.03', 'Despesa Comercial'),
            ('5.1.01', 'Custo Operacional'), ('5.1.02', 'Custo Armazenagem')
        ]
        conn.executemany('INSERT INTO contas_contabeis(codigo,nome) VALUES(?,?)', contas)

    if conn.execute('SELECT COUNT(*) c FROM roles').fetchone()['c'] == 0:
        conn.executemany('INSERT INTO roles(name) VALUES(?)', [('OPERADOR',), ('GESTOR',), ('DIRETORIA',)])
    if conn.execute('SELECT COUNT(*) c FROM permissions').fetchone()['c'] == 0:
        perms = [
            ('planning.read',), ('planning.write',), ('planning.fill.read',), ('planning.fill.write',),
            ('parametros.read',), ('parametros.write',)
        ]
        conn.executemany('INSERT INTO permissions(key) VALUES(?)', perms)

    if conn.execute('SELECT COUNT(*) c FROM role_permissions').fetchone()['c'] == 0:
        role_id = {r['name']: r['id'] for r in conn.execute('SELECT * FROM roles').fetchall()}
        perm_id = {p['key']: p['id'] for p in conn.execute('SELECT * FROM permissions').fetchall()}
        map_rows = [
            (role_id['OPERADOR'], perm_id['planning.read']),
            (role_id['OPERADOR'], perm_id['planning.fill.read']),
            (role_id['OPERADOR'], perm_id['planning.fill.write']),
            (role_id['GESTOR'], perm_id['planning.read']),
            (role_id['GESTOR'], perm_id['planning.write']),
            (role_id['GESTOR'], perm_id['planning.fill.read']),
            (role_id['GESTOR'], perm_id['planning.fill.write']),
        ]
        for pid in perm_id.values():
            map_rows.append((role_id['DIRETORIA'], pid))
        conn.executemany('INSERT INTO role_permissions(roleId, permissionId) VALUES(?,?)', map_rows)

    if conn.execute('SELECT COUNT(*) c FROM users').fetchone()['c'] == 0:
        conn.executemany('INSERT INTO users(nome,email) VALUES(?,?)', [
            ('Ana Diretoria', 'diretoria@coop.local'),
            ('Bruno Gestor', 'gestor@coop.local'),
            ('Carla Operadora', 'operador@coop.local')
        ])

    if conn.execute('SELECT COUNT(*) c FROM user_roles').fetchone()['c'] == 0:
        users = {u['email']: u['id'] for u in conn.execute('SELECT * FROM users').fetchall()}
        roles = {r['name']: r['id'] for r in conn.execute('SELECT * FROM roles').fetchall()}
        conn.executemany('INSERT INTO user_roles(userId, roleId) VALUES(?,?)', [
            (users['diretoria@coop.local'], roles['DIRETORIA']),
            (users['gestor@coop.local'], roles['GESTOR']),
            (users['operador@coop.local'], roles['OPERADOR'])
        ])

    if conn.execute('SELECT COUNT(*) c FROM user_cost_centers').fetchone()['c'] == 0:
        users = {u['email']: u['id'] for u in conn.execute('SELECT * FROM users').fetchall()}
        cc = {r['nome']: r['id'] for r in conn.execute('SELECT * FROM centros_custo').fetchall()}
        conn.executemany('INSERT INTO user_cost_centers(userId, costCenterId, linkType) VALUES(?,?,?)', [
            (users['gestor@coop.local'], cc['Administração'], 'GESTOR'),
            (users['gestor@coop.local'], cc['Comercial'], 'GESTOR'),
            (users['operador@coop.local'], cc['Administração'], 'OPERADOR')
        ])


# Formula logic

def refs(formula):
    return list(set(re.findall(r'L\d{3}', formula or '')))


def build_formula_graph(linhas):
    by_code = {l['codigo']: l for l in linhas}
    graph = {}
    for linha in linhas:
        if linha['tipoLinha'] != 'formula':
            continue
        r = refs(linha['formula'] or '')
        if linha['codigo'] in r:
            raise ValueError(f"A linha {linha['codigo']} não pode referenciar a si própria.")
        for ref in r:
            if ref not in by_code:
                raise ValueError(f"Referência inválida {ref} na linha {linha['codigo']}.")
        graph[linha['codigo']] = [ref for ref in r if by_code[ref]['tipoLinha'] == 'formula']

    vis, stack = set(), set()

    def dfs(node):
        if node in stack:
            raise ValueError('Dependência circular detectada entre linhas de fórmula.')
        if node in vis:
            return
        stack.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        stack.remove(node)
        vis.add(node)

    for node in graph:
        dfs(node)
    return graph


def topological_formula_order(linhas):
    graph = build_formula_graph(linhas)
    formula_codes = {l['codigo'] for l in linhas if l['tipoLinha'] == 'formula'}
    indegree = {code: 0 for code in formula_codes}
    adjacency = {code: [] for code in formula_codes}
    for formula_code, deps in graph.items():
        for dep in deps:
            indegree[formula_code] += 1
            adjacency[dep].append(formula_code)
    queue = deque([code for code in formula_codes if indegree[code] == 0])
    ordered = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for nxt in adjacency[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(ordered) != len(formula_codes):
        raise ValueError('Dependência circular detectada entre linhas de fórmula.')
    return ordered


def validate_formulas(linhas):
    build_formula_graph(linhas)


def eval_formula(formula, values):
    expr = re.sub(r'SOMAR\(([^)]*)\)', lambda m: 'SOMA(' + m.group(1) + ')', (formula or ''), flags=re.I)
    expr = re.sub(r'SOMA\(([^)]*)\)', lambda m: '(' + m.group(1).replace(',', '+') + ')', expr, flags=re.I)
    expr = re.sub(r'L\d{3}', lambda m: str(values.get(m.group(0), 0)), expr)
    if not re.fullmatch(r'[0-9+\-*/().\s]+', expr):
        raise ValueError('Fórmula inválida')
    try:
        return float(eval(expr, {'__builtins__': {}}, {}))
    except Exception:
        return 0.0


def recalc(conn, modelo_id, cc_id, ano):
    linhas = conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (modelo_id,)).fetchall()
    formula_order = topological_formula_order(linhas)
    by_code = {l['codigo']: l for l in linhas}

    rows = conn.execute(
        '''SELECT vm.* FROM valores_mensais vm
           JOIN linhas_modelo l ON l.id=vm.linhaId
           WHERE l.modeloId=? AND vm.centroCustoId=? AND vm.ano=?''',
        (modelo_id, cc_id, ano)
    ).fetchall()
    val = {(r['linhaId'], r['mes']): r['valor'] for r in rows}

    for mes in range(1, 13):
        codes = {}
        for linha in linhas:
            if linha['tipoLinha'] == 'input':
                codes[linha['codigo']] = float(val.get((linha['id'], mes), 0))
        for code in formula_order:
            linha = by_code[code]
            codes[code] = eval_formula(linha['formula'], codes)
            conn.execute(
                '''INSERT INTO valores_mensais(linhaId,centroCustoId,ano,mes,valor,origem,atualizadoEm)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(linhaId,centroCustoId,ano,mes)
                   DO UPDATE SET valor=excluded.valor,origem='calculado',atualizadoEm=excluded.atualizadoEm''',
                (linha['id'], cc_id, ano, mes, codes[code], 'calculado', now())
            )


class Handler(BaseHTTPRequestHandler):
    def json(self, data, status=200):
        b = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        ln = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(ln).decode() if ln else '{}'
        return json.loads(raw or '{}')

    def current_user(self, conn, q):
        # mock session by header or query
        uid = self.headers.get('X-User-Id') or (q.get('userId', [None])[0] if q else None)
        if not uid:
            return None
        user = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        return dict(user) if user else None

    def user_roles(self, conn, user_id):
        return [r['name'] for r in conn.execute(
            'SELECT r.name FROM roles r JOIN user_roles ur ON ur.roleId=r.id WHERE ur.userId=?', (user_id,)
        ).fetchall()]

    def user_permissions(self, conn, user_id):
        return {p['key'] for p in conn.execute(
            '''SELECT p.key FROM permissions p
               JOIN role_permissions rp ON rp.permissionId=p.id
               JOIN user_roles ur ON ur.roleId=rp.roleId
               WHERE ur.userId=?''',
            (user_id,)
        ).fetchall()}

    def is_diretoria(self, conn, user_id):
        return 'DIRETORIA' in self.user_roles(conn, user_id)

    def can_access_cc(self, conn, user_id, cc_id):
        if self.is_diretoria(conn, user_id):
            return True
        row = conn.execute('SELECT 1 x FROM user_cost_centers WHERE userId=? AND costCenterId=?', (user_id, cc_id)).fetchone()
        return bool(row)

    def require_perm(self, conn, q, perm, cc_id=None):
        user = self.current_user(conn, q)
        if not user:
            return None, {'error': 'Usuário não autenticado.'}, 401
        perms = self.user_permissions(conn, user['id'])
        if perm not in perms:
            return None, {'error': 'Acesso negado (sem permissão).'}, 403
        if cc_id is not None and not self.can_access_cc(conn, user['id'], cc_id):
            return None, {'error': 'Acesso negado ao Centro de Custo informado.'}, 403
        return user, None, None

    def paginate(self, q, d_page=1, d_size=20):
        page = int(q.get('page', [str(d_page)])[0])
        size = int(q.get('pageSize', [str(d_size)])[0])
        return page, size, (page - 1) * size

    # ---- GET ----
    def do_GET(self):
        p = urlparse(self.path)
        path = p.path
        q = parse_qs(p.query)
        with db_conn() as conn:
            # Public login helper
            if path == '/api/session/users':
                return self.json([dict(r) for r in conn.execute('SELECT id,nome,email FROM users ORDER BY id')])
            if path == '/api/session/me':
                user = self.current_user(conn, q)
                if not user:
                    return self.json({'error': 'Usuário não autenticado.'}, 401)
                roles = self.user_roles(conn, user['id'])
                return self.json({'user': user, 'roles': roles})

            if path == '/api/my-cost-centers':
                user, err, code = self.require_perm(conn, q, 'planning.fill.read')
                if err:
                    return self.json(err, code)
                if self.is_diretoria(conn, user['id']):
                    items = [dict(r) for r in conn.execute('SELECT * FROM centros_custo ORDER BY nome')]
                else:
                    items = [dict(r) for r in conn.execute(
                        '''SELECT c.* FROM centros_custo c
                           JOIN user_cost_centers ucc ON ucc.costCenterId=c.id
                           WHERE ucc.userId=? ORDER BY c.nome''',
                        (user['id'],)
                    )]
                return self.json(items)

            if path == '/api/contas-contabeis':
                _, err, code = self.require_perm(conn, q, 'planning.read')
                if err:
                    return self.json(err, code)
                return self.json([dict(r) for r in conn.execute('SELECT * FROM contas_contabeis ORDER BY codigo')])

            if path == '/api/centros-custo':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                page, size, off = self.paginate(q)
                total = conn.execute('SELECT COUNT(*) c FROM centros_custo').fetchone()['c']
                items = [dict(r) for r in conn.execute('SELECT * FROM centros_custo ORDER BY nome LIMIT ? OFFSET ?', (size, off))]
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})

            if path == '/api/planejamentos':
                _, err, code = self.require_perm(conn, q, 'planning.read')
                if err:
                    return self.json(err, code)
                page, size, off = self.paginate(q, d_size=10)
                total = conn.execute('SELECT COUNT(*) c FROM planejamentos').fetchone()['c']
                items = [dict(r) for r in conn.execute('SELECT * FROM planejamentos ORDER BY ano DESC, atualizadoEm DESC LIMIT ? OFFSET ?', (size, off))]
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})

            if path == '/api/parametros/usuarios':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                page, size, off = self.paginate(q)
                search = (q.get('q', [''])[0] or '').strip().lower()
                where = 'WHERE lower(nome) LIKE ? OR lower(email) LIKE ?' if search else ''
                params = [f'%{search}%', f'%{search}%'] if search else []
                total = conn.execute(f'SELECT COUNT(*) c FROM users {where}', params).fetchone()['c']
                items = [dict(r) for r in conn.execute(f'SELECT * FROM users {where} ORDER BY id LIMIT ? OFFSET ?', (*params, size, off))]
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})

            if path == '/api/parametros/roles':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                return self.json([dict(r) for r in conn.execute('SELECT * FROM roles ORDER BY id')])

            if path == '/api/parametros/permissions':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                return self.json([dict(r) for r in conn.execute('SELECT * FROM permissions ORDER BY key')])

            if path == '/api/parametros/user-roles':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                items = [dict(r) for r in conn.execute(
                    '''SELECT ur.userId, u.nome as userNome, ur.roleId, r.name as roleName
                       FROM user_roles ur JOIN users u ON u.id=ur.userId JOIN roles r ON r.id=ur.roleId
                       ORDER BY u.id, r.id'''
                )]
                return self.json(items)

            if path == '/api/parametros/role-permissions':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                items = [dict(r) for r in conn.execute(
                    '''SELECT rp.roleId, r.name as roleName, rp.permissionId, p.key as permissionKey
                       FROM role_permissions rp JOIN roles r ON r.id=rp.roleId JOIN permissions p ON p.id=rp.permissionId
                       ORDER BY r.id, p.key'''
                )]
                return self.json(items)

            if path == '/api/parametros/user-cost-centers':
                _, err, code = self.require_perm(conn, q, 'parametros.read')
                if err:
                    return self.json(err, code)
                items = [dict(r) for r in conn.execute(
                    '''SELECT ucc.userId, u.nome as userNome, ucc.costCenterId, c.nome as costCenterNome, ucc.linkType
                       FROM user_cost_centers ucc JOIN users u ON u.id=ucc.userId JOIN centros_custo c ON c.id=ucc.costCenterId
                       ORDER BY u.id, c.nome'''
                )]
                return self.json(items)

            if m := re.match(r'^/api/planejamentos/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'planning.read')
                if err:
                    return self.json(err, code)
                r = conn.execute('SELECT * FROM planejamentos WHERE id=?', (m.group(1),)).fetchone()
                return self.json(dict(r) if r else {'error': 'Planejamento não encontrado.'}, 200 if r else 404)

            if m := re.match(r'^/api/planejamentos/(\d+)/modelos$', path):
                _, err, code = self.require_perm(conn, q, 'planning.read')
                if err:
                    return self.json(err, code)
                page, size, off = self.paginate(q)
                total = conn.execute('SELECT COUNT(*) c FROM modelos WHERE planejamentoId=?', (m.group(1),)).fetchone()['c']
                items = [dict(r) for r in conn.execute('SELECT * FROM modelos WHERE planejamentoId=? ORDER BY ordem LIMIT ? OFFSET ?', (m.group(1), size, off))]
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})

            if m := re.match(r'^/api/modelos/(\d+)/linhas$', path):
                _, err, code = self.require_perm(conn, q, 'planning.read')
                if err:
                    return self.json(err, code)
                page, size, off = self.paginate(q, d_size=100)
                total = conn.execute('SELECT COUNT(*) c FROM linhas_modelo WHERE modeloId=?', (m.group(1),)).fetchone()['c']
                items = [dict(r) for r in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem LIMIT ? OFFSET ?', (m.group(1), size, off))]
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})

            if m := re.match(r'^/api/modelos/(\d+)/valores$', path):
                cc = int(q.get('centroCustoId', ['0'])[0])
                ano = int(q.get('ano', ['0'])[0])
                _, err, code = self.require_perm(conn, q, 'planning.fill.read', cc_id=cc if cc > 0 else None)
                if err:
                    return self.json(err, code)
                if ano <= 0 or cc <= 0:
                    return self.json({'error': 'Parâmetros centroCustoId e ano são obrigatórios.'}, 400)
                linhas = [dict(r) for r in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (m.group(1),))]
                vals = [dict(r) for r in conn.execute(
                    '''SELECT vm.* FROM valores_mensais vm JOIN linhas_modelo l ON l.id=vm.linhaId
                       WHERE l.modeloId=? AND vm.centroCustoId=? AND vm.ano=?''',
                    (m.group(1), cc, ano)
                )]
                return self.json({'linhas': linhas, 'valores': vals})

        return self.serve_front(path)

    # ---- POST ----
    def do_POST(self):
        p = urlparse(self.path)
        path = p.path
        q = parse_qs(p.query)
        data = self.body()
        with db_conn() as conn:
            if path == '/api/planejamentos':
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                ts = now()
                cur = conn.execute('INSERT INTO planejamentos(nome,ano,status,criadoEm,atualizadoEm) VALUES(?,?,?,?,?)', (data['nome'], data['ano'], 'draft', ts, ts))
                return self.json(dict(conn.execute('SELECT * FROM planejamentos WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

            if m := re.match(r'^/api/planejamentos/(\d+)/copy$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                origem = int(m.group(1))
                ts = now()
                novo = conn.execute('INSERT INTO planejamentos(nome,ano,status,criadoEm,atualizadoEm) VALUES(?,?,?,?,?)', (data['nome'], data['ano'], 'draft', ts, ts)).lastrowid
                for mod in conn.execute('SELECT * FROM modelos WHERE planejamentoId=? ORDER BY ordem', (origem,)).fetchall():
                    m2 = conn.execute('INSERT INTO modelos(planejamentoId,nome,tipo,descricao,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?)', (novo, mod['nome'], mod['tipo'], mod['descricao'], mod['ordem'], ts, ts)).lastrowid
                    for ln in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (mod['id'],)).fetchall():
                        conn.execute('INSERT INTO linhas_modelo(modeloId,codigo,nomeLinha,tipoLinha,formato,formula,referencia,contaContabilId,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?,?,?,?,?)', (m2, ln['codigo'], ln['nomeLinha'], ln['tipoLinha'], ln['formato'], ln['formula'], ln['referencia'], ln['contaContabilId'], ln['ordem'], ts, ts))
                return self.json(dict(conn.execute('SELECT * FROM planejamentos WHERE id=?', (novo,)).fetchone()), 201)

            if m := re.match(r'^/api/planejamentos/(\d+)/modelos$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                ts = now()
                od = conn.execute('SELECT COALESCE(MAX(ordem),0)+1 o FROM modelos WHERE planejamentoId=?', (m.group(1),)).fetchone()['o']
                cur = conn.execute('INSERT INTO modelos(planejamentoId,nome,tipo,descricao,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?)', (m.group(1), data['nome'], data['tipo'], data.get('descricao'), od, ts, ts))
                return self.json(dict(conn.execute('SELECT * FROM modelos WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

            if m := re.match(r'^/api/modelos/(\d+)/linhas$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                if data.get('tipoLinha') == 'formula' and not (data.get('formula') or '').strip():
                    return self.json({'error': 'Fórmula é obrigatória para tipo formula.'}, 400)
                ts = now()
                od = conn.execute('SELECT COALESCE(MAX(ordem),0)+1 o FROM linhas_modelo WHERE modeloId=?', (m.group(1),)).fetchone()['o']
                cur = conn.execute('INSERT INTO linhas_modelo(modeloId,codigo,nomeLinha,tipoLinha,formato,formula,referencia,contaContabilId,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?,?,?,?,?)', (m.group(1), data['codigo'], data['nomeLinha'], data['tipoLinha'], data['formato'], data.get('formula'), None, data.get('contaContabilId'), od, ts, ts))
                linhas = conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=?', (m.group(1),)).fetchall()
                try:
                    validate_formulas(linhas)
                except ValueError as e:
                    conn.execute('DELETE FROM linhas_modelo WHERE id=?', (cur.lastrowid,))
                    return self.json({'error': str(e)}, 400)
                return self.json(dict(conn.execute('SELECT * FROM linhas_modelo WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

            if m := re.match(r'^/api/modelos/(\d+)/linhas/reorder$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                for i, lid in enumerate(data['orderedIds']):
                    conn.execute('UPDATE linhas_modelo SET ordem=? WHERE id=? AND modeloId=?', (i + 1, lid, m.group(1)))
                items = [dict(r) for r in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (m.group(1),))]
                return self.json(items)

            if m := re.match(r'^/api/modelos/(\d+)/valores/upsert$', path):
                cc = int(data.get('centroCustoId') or 0)
                _, err, code = self.require_perm(conn, q, 'planning.fill.write', cc_id=cc if cc > 0 else None)
                if err:
                    return self.json(err, code)
                ano = int(data.get('ano') or 0)
                if ano <= 0 or cc <= 0:
                    return self.json({'error': 'Campos ano e centroCustoId são obrigatórios.'}, 400)
                for u in data['updates']:
                    conn.execute(
                        '''INSERT INTO valores_mensais(linhaId,centroCustoId,ano,mes,valor,origem,atualizadoEm) VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(linhaId,centroCustoId,ano,mes)
                           DO UPDATE SET valor=excluded.valor,origem='manual',atualizadoEm=excluded.atualizadoEm''',
                        (u['linhaId'], cc, ano, u['mes'], float(u['valor']), 'manual', now())
                    )
                recalc(conn, int(m.group(1)), cc, ano)
                return self.json({'ok': True})

            # Parâmetros CRUD
            if path == '/api/parametros/usuarios':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                cur = conn.execute('INSERT INTO users(nome,email) VALUES(?,?)', (data['nome'], data['email']))
                return self.json(dict(conn.execute('SELECT * FROM users WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

            if path == '/api/parametros/roles':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                cur = conn.execute('INSERT INTO roles(name) VALUES(?)', (data['name'],))
                return self.json(dict(conn.execute('SELECT * FROM roles WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

            if path == '/api/parametros/permissions':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                cur = conn.execute('INSERT INTO permissions(key) VALUES(?)', (data['key'],))
                return self.json(dict(conn.execute('SELECT * FROM permissions WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

            if path == '/api/parametros/user-roles':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('INSERT OR REPLACE INTO user_roles(userId,roleId) VALUES(?,?)', (data['userId'], data['roleId']))
                return self.json({'ok': True}, 201)

            if path == '/api/parametros/role-permissions':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('INSERT OR REPLACE INTO role_permissions(roleId,permissionId) VALUES(?,?)', (data['roleId'], data['permissionId']))
                return self.json({'ok': True}, 201)

            if path == '/api/parametros/user-cost-centers':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('INSERT OR REPLACE INTO user_cost_centers(userId,costCenterId,linkType) VALUES(?,?,?)', (data['userId'], data['costCenterId'], data['linkType']))
                return self.json({'ok': True}, 201)

            if path == '/api/centros-custo':
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                cur = conn.execute('INSERT INTO centros_custo(nome) VALUES(?)', (data['nome'],))
                return self.json(dict(conn.execute('SELECT * FROM centros_custo WHERE id=?', (cur.lastrowid,)).fetchone()), 201)

        return self.json({'error': 'Rota não encontrada'}, 404)

    # ---- PUT ----
    def do_PUT(self):
        p = urlparse(self.path)
        path = p.path
        q = parse_qs(p.query)
        data = self.body()
        with db_conn() as conn:
            if m := re.match(r'^/api/modelos/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                conn.execute('UPDATE modelos SET nome=?,tipo=?,descricao=?,atualizadoEm=? WHERE id=?', (data['nome'], data['tipo'], data.get('descricao'), now(), m.group(1)))
                r = conn.execute('SELECT * FROM modelos WHERE id=?', (m.group(1),)).fetchone()
                return self.json(dict(r))

            if m := re.match(r'^/api/linhas/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                if data.get('tipoLinha') == 'formula' and not (data.get('formula') or '').strip():
                    return self.json({'error': 'Fórmula é obrigatória para tipo formula.'}, 400)
                old = conn.execute('SELECT * FROM linhas_modelo WHERE id=?', (m.group(1),)).fetchone()
                if old is None:
                    return self.json({'error': 'Linha não encontrada.'}, 404)
                conn.execute('UPDATE linhas_modelo SET codigo=?,nomeLinha=?,tipoLinha=?,formato=?,formula=?,contaContabilId=?,atualizadoEm=? WHERE id=?', (data['codigo'], data['nomeLinha'], data['tipoLinha'], data['formato'], data.get('formula'), data.get('contaContabilId'), now(), m.group(1)))
                linhas = conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=?', (old['modeloId'],)).fetchall()
                try:
                    validate_formulas(linhas)
                except ValueError as e:
                    conn.execute('UPDATE linhas_modelo SET codigo=?,nomeLinha=?,tipoLinha=?,formato=?,formula=?,contaContabilId=? WHERE id=?', (old['codigo'], old['nomeLinha'], old['tipoLinha'], old['formato'], old['formula'], old['contaContabilId'], m.group(1)))
                    return self.json({'error': str(e)}, 400)
                return self.json(dict(conn.execute('SELECT * FROM linhas_modelo WHERE id=?', (m.group(1),)).fetchone()))

            if m := re.match(r'^/api/parametros/usuarios/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('UPDATE users SET nome=?, email=? WHERE id=?', (data['nome'], data['email'], m.group(1)))
                return self.json(dict(conn.execute('SELECT * FROM users WHERE id=?', (m.group(1),)).fetchone()))

            if m := re.match(r'^/api/centros-custo/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('UPDATE centros_custo SET nome=? WHERE id=?', (data['nome'], m.group(1)))
                return self.json(dict(conn.execute('SELECT * FROM centros_custo WHERE id=?', (m.group(1),)).fetchone()))

        return self.json({'error': 'Rota não encontrada'}, 404)

    # ---- DELETE ----
    def do_DELETE(self):
        p = urlparse(self.path)
        path = p.path
        q = parse_qs(p.query)
        with db_conn() as conn:
            if m := re.match(r'^/api/linhas/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                conn.execute('DELETE FROM linhas_modelo WHERE id=?', (m.group(1),))
                self.send_response(204); self.end_headers(); return

            if m := re.match(r'^/api/modelos/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'planning.write')
                if err:
                    return self.json(err, code)
                mid = int(m.group(1))
                model = conn.execute('SELECT m.*, p.status FROM modelos m JOIN planejamentos p ON p.id=m.planejamentoId WHERE m.id=?', (mid,)).fetchone()
                if not model:
                    return self.json({'error': 'Modelo não encontrado.'}, 404)
                if model['status'] != 'draft':
                    return self.json({'error': 'Somente planejamento draft permite excluir modelo.'}, 400)
                count = conn.execute('SELECT COUNT(*) c FROM valores_mensais vm JOIN linhas_modelo l ON l.id=vm.linhaId WHERE l.modeloId=?', (mid,)).fetchone()['c']
                if count > 0:
                    return self.json({'error': 'Modelo possui valores e não pode ser excluído.'}, 400)
                conn.execute('DELETE FROM modelos WHERE id=?', (mid,))
                self.send_response(204); self.end_headers(); return

            if m := re.match(r'^/api/parametros/usuarios/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('DELETE FROM users WHERE id=?', (m.group(1),))
                self.send_response(204); self.end_headers(); return

            if m := re.match(r'^/api/centros-custo/(\d+)$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                conn.execute('DELETE FROM centros_custo WHERE id=?', (m.group(1),))
                self.send_response(204); self.end_headers(); return

            if m := re.match(r'^/api/parametros/user-roles$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                ln = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(ln).decode() if ln else '{}')
                conn.execute('DELETE FROM user_roles WHERE userId=? AND roleId=?', (data['userId'], data['roleId']))
                self.send_response(204); self.end_headers(); return

            if m := re.match(r'^/api/parametros/role-permissions$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                ln = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(ln).decode() if ln else '{}')
                conn.execute('DELETE FROM role_permissions WHERE roleId=? AND permissionId=?', (data['roleId'], data['permissionId']))
                self.send_response(204); self.end_headers(); return

            if m := re.match(r'^/api/parametros/user-cost-centers$', path):
                _, err, code = self.require_perm(conn, q, 'parametros.write')
                if err:
                    return self.json(err, code)
                ln = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(ln).decode() if ln else '{}')
                conn.execute('DELETE FROM user_cost_centers WHERE userId=? AND costCenterId=?', (data['userId'], data['costCenterId']))
                self.send_response(204); self.end_headers(); return

        return self.json({'error': 'Rota não encontrada'}, 404)

    def serve_front(self, path):
        if path.startswith('/styles.css'):
            f = PUBLIC / 'styles.css'; ctype = 'text/css'
        elif path.startswith('/app.js'):
            f = PUBLIC / 'app.js'; ctype = 'application/javascript'
        else:
            f = PUBLIC / 'index.html'; ctype = 'text/html'
        data = f.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    init_db()
    srv = HTTPServer(('0.0.0.0', 3000), Handler)
    print('Servidor em http://localhost:3000')
    srv.serve_forever()
