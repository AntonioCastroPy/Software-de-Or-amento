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
            CREATE TABLE IF NOT EXISTS centros_custo (id INTEGER PRIMARY KEY AUTOINCREMENT,nome TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS contas_contabeis (id INTEGER PRIMARY KEY AUTOINCREMENT,codigo TEXT UNIQUE NOT NULL,nome TEXT NOT NULL);
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
            """
        )
        ensure_valores_schema(conn)

        if conn.execute('SELECT COUNT(*) c FROM centros_custo').fetchone()['c'] == 0:
            conn.executemany('INSERT INTO centros_custo(nome) VALUES(?)', [('Administração',), ('Armazém',), ('Comercial',)])
        if conn.execute('SELECT COUNT(*) c FROM contas_contabeis').fetchone()['c'] == 0:
            contas = [
                ('1.1.01', 'Caixa'),
                ('1.1.02', 'Bancos'),
                ('2.1.01', 'Fornecedores'),
                ('3.1.01', 'Receita Venda Milho'),
                ('3.1.02', 'Receita Venda Soja'),
                ('4.1.01', 'Despesa Administrativa'),
                ('4.1.02', 'Despesa Logística'),
                ('4.1.03', 'Despesa Comercial'),
                ('5.1.01', 'Custo Operacional'),
                ('5.1.02', 'Custo Armazenagem'),
            ]
            conn.executemany('INSERT INTO contas_contabeis(codigo,nome) VALUES(?,?)', contas)


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

    def do_GET(self):
        p = urlparse(self.path)
        path = p.path
        q = parse_qs(p.query)
        with db_conn() as conn:
            if path == '/api/centros-custo':
                return self.json([dict(r) for r in conn.execute('SELECT * FROM centros_custo ORDER BY id')])
            if path == '/api/contas-contabeis':
                return self.json([dict(r) for r in conn.execute('SELECT * FROM contas_contabeis ORDER BY codigo')])
            if path == '/api/planejamentos':
                page, size = int(q.get('page', ['1'])[0]), int(q.get('pageSize', ['10'])[0])
                off = (page - 1) * size
                items = [dict(r) for r in conn.execute('SELECT * FROM planejamentos ORDER BY ano DESC, atualizadoEm DESC LIMIT ? OFFSET ?', (size, off))]
                total = conn.execute('SELECT COUNT(*) c FROM planejamentos').fetchone()['c']
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})
            if m := re.match(r'^/api/planejamentos/(\d+)$', path):
                r = conn.execute('SELECT * FROM planejamentos WHERE id=?', (m.group(1),)).fetchone()
                return self.json(dict(r) if r else {'error': 'Planejamento não encontrado.'}, 200 if r else 404)
            if m := re.match(r'^/api/planejamentos/(\d+)/modelos$', path):
                page, size = int(q.get('page', ['1'])[0]), int(q.get('pageSize', ['20'])[0])
                off = (page - 1) * size
                items = [dict(r) for r in conn.execute('SELECT * FROM modelos WHERE planejamentoId=? ORDER BY ordem LIMIT ? OFFSET ?', (m.group(1), size, off))]
                total = conn.execute('SELECT COUNT(*) c FROM modelos WHERE planejamentoId=?', (m.group(1),)).fetchone()['c']
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})
            if m := re.match(r'^/api/modelos/(\d+)/linhas$', path):
                page, size = int(q.get('page', ['1'])[0]), int(q.get('pageSize', ['100'])[0])
                off = (page - 1) * size
                items = [dict(r) for r in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem LIMIT ? OFFSET ?', (m.group(1), size, off))]
                total = conn.execute('SELECT COUNT(*) c FROM linhas_modelo WHERE modeloId=?', (m.group(1),)).fetchone()['c']
                return self.json({'items': items, 'total': total, 'page': page, 'pageSize': size})
            if m := re.match(r'^/api/modelos/(\d+)/valores$', path):
                cc = int(q.get('centroCustoId', ['1'])[0])
                ano = int(q.get('ano', ['0'])[0])
                if ano <= 0:
                    return self.json({'error': 'Parâmetro ano é obrigatório.'}, 400)
                linhas = [dict(r) for r in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (m.group(1),))]
                vals = [
                    dict(r) for r in conn.execute(
                        '''SELECT vm.* FROM valores_mensais vm
                           JOIN linhas_modelo l ON l.id=vm.linhaId
                           WHERE l.modeloId=? AND vm.centroCustoId=? AND vm.ano=?''',
                        (m.group(1), cc, ano)
                    )
                ]
                return self.json({'linhas': linhas, 'valores': vals})

        return self.serve_front(path)

    def do_POST(self):
        p = urlparse(self.path).path
        data = self.body()
        with db_conn() as conn:
            if p == '/api/planejamentos':
                ts = now()
                cur = conn.execute('INSERT INTO planejamentos(nome,ano,status,criadoEm,atualizadoEm) VALUES(?,?,?,?,?)', (data['nome'], data['ano'], 'draft', ts, ts))
                r = conn.execute('SELECT * FROM planejamentos WHERE id=?', (cur.lastrowid,)).fetchone()
                return self.json(dict(r), 201)
            if m := re.match(r'^/api/planejamentos/(\d+)/copy$', p):
                origem = int(m.group(1))
                ts = now()
                cur = conn.execute('INSERT INTO planejamentos(nome,ano,status,criadoEm,atualizadoEm) VALUES(?,?,?,?,?)', (data['nome'], data['ano'], 'draft', ts, ts))
                novo = cur.lastrowid
                for mod in conn.execute('SELECT * FROM modelos WHERE planejamentoId=? ORDER BY ordem', (origem,)).fetchall():
                    m2 = conn.execute(
                        'INSERT INTO modelos(planejamentoId,nome,tipo,descricao,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?)',
                        (novo, mod['nome'], mod['tipo'], mod['descricao'], mod['ordem'], ts, ts)
                    ).lastrowid
                    for ln in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (mod['id'],)).fetchall():
                        conn.execute(
                            'INSERT INTO linhas_modelo(modeloId,codigo,nomeLinha,tipoLinha,formato,formula,referencia,contaContabilId,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (m2, ln['codigo'], ln['nomeLinha'], ln['tipoLinha'], ln['formato'], ln['formula'], ln['referencia'], ln['contaContabilId'], ln['ordem'], ts, ts)
                        )
                r = conn.execute('SELECT * FROM planejamentos WHERE id=?', (novo,)).fetchone()
                return self.json(dict(r), 201)
            if m := re.match(r'^/api/planejamentos/(\d+)/modelos$', p):
                ts = now()
                od = conn.execute('SELECT COALESCE(MAX(ordem),0)+1 o FROM modelos WHERE planejamentoId=?', (m.group(1),)).fetchone()['o']
                cur = conn.execute(
                    'INSERT INTO modelos(planejamentoId,nome,tipo,descricao,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?)',
                    (m.group(1), data['nome'], data['tipo'], data.get('descricao'), od, ts, ts)
                )
                r = conn.execute('SELECT * FROM modelos WHERE id=?', (cur.lastrowid,)).fetchone()
                return self.json(dict(r), 201)
            if m := re.match(r'^/api/modelos/(\d+)/linhas$', p):
                if data.get('tipoLinha') == 'formula' and not (data.get('formula') or '').strip():
                    return self.json({'error': 'Fórmula é obrigatória para tipo formula.'}, 400)
                ts = now()
                od = conn.execute('SELECT COALESCE(MAX(ordem),0)+1 o FROM linhas_modelo WHERE modeloId=?', (m.group(1),)).fetchone()['o']
                cur = conn.execute(
                    'INSERT INTO linhas_modelo(modeloId,codigo,nomeLinha,tipoLinha,formato,formula,referencia,contaContabilId,ordem,criadoEm,atualizadoEm) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (m.group(1), data['codigo'], data['nomeLinha'], data['tipoLinha'], data['formato'], data.get('formula'), None, data.get('contaContabilId'), od, ts, ts)
                )
                linhas = conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=?', (m.group(1),)).fetchall()
                try:
                    validate_formulas(linhas)
                except ValueError as e:
                    conn.execute('DELETE FROM linhas_modelo WHERE id=?', (cur.lastrowid,))
                    return self.json({'error': str(e)}, 400)
                r = conn.execute('SELECT * FROM linhas_modelo WHERE id=?', (cur.lastrowid,)).fetchone()
                return self.json(dict(r), 201)
            if m := re.match(r'^/api/modelos/(\d+)/linhas/reorder$', p):
                for i, lid in enumerate(data['orderedIds']):
                    conn.execute('UPDATE linhas_modelo SET ordem=? WHERE id=? AND modeloId=?', (i + 1, lid, m.group(1)))
                items = [dict(r) for r in conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=? ORDER BY ordem', (m.group(1),))]
                return self.json(items)
            if m := re.match(r'^/api/modelos/(\d+)/valores/upsert$', p):
                ano = int(data.get('ano') or 0)
                if ano <= 0:
                    return self.json({'error': 'Campo ano é obrigatório.'}, 400)
                for u in data['updates']:
                    conn.execute(
                        '''INSERT INTO valores_mensais(linhaId,centroCustoId,ano,mes,valor,origem,atualizadoEm) VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(linhaId,centroCustoId,ano,mes) DO UPDATE SET valor=excluded.valor,origem='manual',atualizadoEm=excluded.atualizadoEm''',
                        (u['linhaId'], data['centroCustoId'], ano, u['mes'], float(u['valor']), 'manual', now())
                    )
                recalc(conn, int(m.group(1)), int(data['centroCustoId']), ano)
                return self.json({'ok': True})
        return self.json({'error': 'Rota não encontrada'}, 404)

    def do_PUT(self):
        p = urlparse(self.path).path
        data = self.body()
        with db_conn() as conn:
            if m := re.match(r'^/api/modelos/(\d+)$', p):
                conn.execute('UPDATE modelos SET nome=?,tipo=?,descricao=?,atualizadoEm=? WHERE id=?', (data['nome'], data['tipo'], data.get('descricao'), now(), m.group(1)))
                r = conn.execute('SELECT * FROM modelos WHERE id=?', (m.group(1),)).fetchone()
                return self.json(dict(r))
            if m := re.match(r'^/api/linhas/(\d+)$', p):
                if data.get('tipoLinha') == 'formula' and not (data.get('formula') or '').strip():
                    return self.json({'error': 'Fórmula é obrigatória para tipo formula.'}, 400)
                old = conn.execute('SELECT * FROM linhas_modelo WHERE id=?', (m.group(1),)).fetchone()
                if old is None:
                    return self.json({'error': 'Linha não encontrada.'}, 404)
                conn.execute(
                    'UPDATE linhas_modelo SET codigo=?,nomeLinha=?,tipoLinha=?,formato=?,formula=?,contaContabilId=?,atualizadoEm=? WHERE id=?',
                    (data['codigo'], data['nomeLinha'], data['tipoLinha'], data['formato'], data.get('formula'), data.get('contaContabilId'), now(), m.group(1))
                )
                linhas = conn.execute('SELECT * FROM linhas_modelo WHERE modeloId=?', (old['modeloId'],)).fetchall()
                try:
                    validate_formulas(linhas)
                except ValueError as e:
                    conn.execute(
                        'UPDATE linhas_modelo SET codigo=?,nomeLinha=?,tipoLinha=?,formato=?,formula=?,contaContabilId=? WHERE id=?',
                        (old['codigo'], old['nomeLinha'], old['tipoLinha'], old['formato'], old['formula'], old['contaContabilId'], m.group(1))
                    )
                    return self.json({'error': str(e)}, 400)
                r = conn.execute('SELECT * FROM linhas_modelo WHERE id=?', (m.group(1),)).fetchone()
                return self.json(dict(r))
        return self.json({'error': 'Rota não encontrada'}, 404)

    def do_DELETE(self):
        p = urlparse(self.path).path
        with db_conn() as conn:
            if m := re.match(r'^/api/linhas/(\d+)$', p):
                conn.execute('DELETE FROM linhas_modelo WHERE id=?', (m.group(1),))
                self.send_response(204)
                self.end_headers()
                return
            if m := re.match(r'^/api/modelos/(\d+)$', p):
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
                self.send_response(204)
                self.end_headers()
                return
        return self.json({'error': 'Rota não encontrada'}, 404)

    def serve_front(self, path):
        if path.startswith('/styles.css'):
            f = PUBLIC / 'styles.css'
            ctype = 'text/css'
        elif path.startswith('/app.js'):
            f = PUBLIC / 'app.js'
            ctype = 'application/javascript'
        else:
            f = PUBLIC / 'index.html'
            ctype = 'text/html'
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
