import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text, bindparam
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unicodedata import normalize
import hashlib
import io
import re
import json

# =========================
# CONFIGURAÇÕES
# =========================
st.set_page_config(
    page_title="Cobrança de Carteira",
    page_icon="📋",
    layout="wide"
)

TZ = ZoneInfo("America/Maceio")

ANALISTAS = {
    "Cleviton": [
        "Portas e Janelas", "Ferramentas", "Ferragens", "Automotivos"
    ],
    "Alec": [
        "Eletrica", "Iluminacao", "Hidraulica"
    ],
    "Jonatas": [
        "Moveis e Colchoes", "Decoracao", "Cama Mesa e Banho", "Lazer",
        "Casa e UD", "Jardim",
    ],
    "Beatriz": [
        "Eletro", "Tecnologia", "Climatizacao"
    ],
    "Ruan": [
        "Tintas", "Organizacao da Casa"
    ],
    "Jessica": [
        "Materiais de Construcao", "Banho e Cozinha"
    ],
    "Rose": [
        "Pisos e Revestimento"
    ],
}

STATUS_PENDENTE = "PENDENTE"
STATUS_COBRADO_1 = "COBRADO 1X"
STATUS_COBRADO_2 = "COBRADO 2X"
STATUS_COBRADO_3 = "COBRADO 3X"
STATUS_ACIONAR_COMPRADOR = "ACIONAR COMPRADOR"
STATUS_COMPRADOR_ACIONADO = "COMPRADOR ACIONADO"
STATUS_FORA_ATRASO = "FORA DO ATRASO"
STATUS_COM_AGENDAMENTO = "COM AGENDAMENTO"
STATUS_CANCELADO = "CANCELADO / RETIRADO"

COLUNAS_MOEDA = [
    "saldo_cmv",
    "pre_nota_cmv",
    "nao_faturado_cmv",
    "saldo_cmv_item",
    "pre_nota_cmv_item",
    "nao_faturado_cmv_item",
    "saldo_cmv_pedido",
    "pre_nota_cmv_pedido",
    "nao_faturado_cmv_pedido",
    "Saldo R$ Item",
    "Pré-nota R$ Item",
    "Não Faturado R$ Item",
    "Saldo R$ Pedido",
    "Pré-nota R$ Pedido",
    "Não Faturado R$ Pedido",
]

CAMPOS_PEDIDOS = [
    "doc_id",
    "pedido",
    "analista",
    "departamento",
    "departamento_norm",
    "fornecedor",
    "dt_agendada",
    "dt_agendada_ordem",
    "saldo_cmv",
    "pre_nota_cmv",
    "nao_faturado_cmv",
    "qtd_itens",
    "ativo",
    "status",
    "cobrancas",
    "comprador_acionado",
    "ultima_cobranca",
    "data_primeira_entrada",
    "data_ultimo_upload",
    "data_cancelamento",
    "criado_em",
    "atualizado_em",
    "itens_json",
]

CAMPOS_LISTAGEM = [
    "doc_id",
    "pedido",
    "analista",
    "departamento",
    "fornecedor",
    "dt_agendada",
    "dt_agendada_ordem",
    "qtd_itens",
    "saldo_cmv",
    "pre_nota_cmv",
    "nao_faturado_cmv",
    "status",
    "cobrancas",
    "ultima_cobranca",
    "data_primeira_entrada",
    "data_ultimo_upload",
    "data_cancelamento",
    "ativo",
]

# =========================
# ESTILO
# =========================
st.markdown("""
<style>
    .main {background-color: #f7f8fb;}
    .block-container {padding-top: 1.2rem;}

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #e8e8ef;
        padding: 16px;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(15,23,42,.04);
    }

    .card {
        background: white;
        border: 1px solid #e8e8ef;
        border-radius: 14px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(15,23,42,.04);
    }

    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid #ddd;
    }

    .pendente {background:#f1f5f9;color:#334155;}
    .ok1 {background:#dbeafe;color:#1d4ed8;}
    .ok2 {background:#fef3c7;color:#92400e;}
    .comprador {background:#fee2e2;color:#991b1b;}
    .acionado {background:#ede9fe;color:#5b21b6;}
    .fora {background:#e2e8f0;color:#475569;}
    .agendado {background:#dbeafe;color:#1e40af;}
    .cancelado {background:#f3f4f6;color:#374151;}
</style>
""", unsafe_allow_html=True)

# =========================
# FUNÇÕES BASE
# =========================
def hoje():
    return datetime.now(TZ).date()


def data_limite_cobranca():
    return hoje() - timedelta(days=1)


def agora_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def data_br(data_obj):
    if not data_obj:
        return ""

    try:
        return data_obj.strftime("%d/%m/%Y")
    except Exception:
        return str(data_obj)


def sem_acento(txt):
    txt = "" if pd.isna(txt) else str(txt)
    return normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")


def norm(txt):
    txt = sem_acento(txt).upper().strip()

    for ch in ["-", "–", "—", "_", ".", "/", "\\", "(", ")", "$", "º", "ª"]:
        txt = txt.replace(ch, " ")

    txt = " ".join(txt.split())
    return txt


def hash_id(*partes):
    texto = "|".join(norm(p) for p in partes if str(p).strip() != "")
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:24]


def converter_data(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, datetime):
        return valor.date()

    if isinstance(valor, pd.Timestamp):
        return valor.date()

    if isinstance(valor, (int, float)):
        try:
            if 30000 <= float(valor) <= 60000:
                dt = pd.to_datetime(valor, unit="D", origin="1899-12-30", errors="coerce")
                if not pd.isna(dt):
                    return dt.date()
        except Exception:
            pass

    txt = str(valor).strip()

    if not txt or txt.lower() in ["nan", "nat", "none", "-"]:
        return None

    dt = pd.to_datetime(txt, dayfirst=True, errors="coerce")

    if pd.isna(dt):
        return None

    return dt.date()


def converter_numero(valor):
    if valor is None or pd.isna(valor):
        return 0.0

    if isinstance(valor, (int, float)):
        return float(valor)

    txt = str(valor).strip()

    if not txt or txt.lower() in ["nan", "none", "-", ""]:
        return 0.0

    txt = txt.replace("R$", "").replace(" ", "")

    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt:
        txt = txt.replace(",", ".")

    try:
        return float(txt)
    except Exception:
        return 0.0


def formatar_moeda(valor):
    try:
        if valor is None or str(valor).strip() == "":
            return "R$ 0,00"

        if isinstance(valor, str) and valor.strip().startswith("R$"):
            return valor

        v = float(valor)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor or "R$ 0,00")


def formatar_df_moeda(df):
    if df is None or df.empty:
        return df

    df_formatado = df.copy()

    for col in COLUNAS_MOEDA:
        if col in df_formatado.columns:
            df_formatado[col] = df_formatado[col].apply(formatar_moeda)

    return df_formatado


def status_por_cobranca(qtd, comprador_acionado=False):
    qtd = int(qtd or 0)

    if comprador_acionado:
        return STATUS_COMPRADOR_ACIONADO

    if qtd <= 0:
        return STATUS_PENDENTE

    if qtd == 1:
        return STATUS_COBRADO_1

    if qtd == 2:
        return STATUS_COBRADO_2

    return STATUS_COBRADO_3


def classe_status(status):
    if status == STATUS_PENDENTE:
        return "pendente"

    if status == STATUS_COBRADO_1:
        return "ok1"

    if status == STATUS_COBRADO_2:
        return "ok2"

    if status == STATUS_COBRADO_3:
        return "ok2"

    if status == STATUS_ACIONAR_COMPRADOR:
        return "comprador"

    if status == STATUS_COMPRADOR_ACIONADO:
        return "acionado"

    if status == STATUS_FORA_ATRASO:
        return "fora"

    if status == STATUS_COM_AGENDAMENTO:
        return "agendado"

    if status == STATUS_CANCELADO:
        return "cancelado"

    return "pendente"


def badge(status):
    css = classe_status(status)
    return f'<span class="badge {css}">{status}</span>'


def identificar_analista(departamento):
    dep_n = norm(departamento)

    for analista, deps in ANALISTAS.items():
        for dep in deps:
            dep_ref = norm(dep)

            if dep_n == dep_ref or dep_ref in dep_n or dep_n in dep_ref:
                return analista

    return "SEM ANALISTA"


def primeiro_valor(series):
    for v in series:
        if v is None or pd.isna(v):
            continue

        txt = str(v).strip()

        if txt and txt.lower() not in ["nan", "none", "-"]:
            return txt

    return ""


def menor_data(series):
    datas = []

    for v in series:
        if v is not None and not pd.isna(v):
            datas.append(v)

    if not datas:
        return None

    return min(datas)


def extrair_pedidos_texto(texto):
    if not texto:
        return []

    txt = str(texto).upper()
    partes = re.split(r"[\s,;|]+", txt)

    pedidos = []

    for p in partes:
        p = p.strip()
        if not p:
            continue
        pedidos.append(norm(p))

    return list(dict.fromkeys(pedidos))


# =========================
# NEON / POSTGRES
# =========================
@st.cache_resource
def conectar_banco():
    if "neon" not in st.secrets or "database_url" not in st.secrets["neon"]:
        st.error("Neon não configurado. Coloque [neon] database_url nos Secrets do Streamlit.")
        st.stop()

    database_url = st.secrets["neon"]["database_url"]

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )


engine = conectar_banco()


def inicializar_banco():
    sql = """
    create table if not exists carteira_pedidos (
        doc_id text primary key,
        pedido text,
        analista text,
        departamento text,
        departamento_norm text,
        fornecedor text,
        dt_agendada text,
        dt_agendada_ordem text,
        saldo_cmv numeric default 0,
        pre_nota_cmv numeric default 0,
        nao_faturado_cmv numeric default 0,
        qtd_itens integer default 0,
        ativo boolean default true,
        status text,
        cobrancas integer default 0,
        comprador_acionado boolean default false,
        ultima_cobranca text,
        data_primeira_entrada text,
        data_ultimo_upload text,
        data_cancelamento text,
        criado_em text,
        atualizado_em text,
        itens_json text default '[]'
    );

    create table if not exists carteira_historico (
        id bigserial primary key,
        doc_id text references carteira_pedidos(doc_id) on delete cascade,
        pedido text,
        tipo text,
        data text,
        usuario text,
        observacao text,
        cobranca_numero integer,
        status_apos text
    );

    alter table carteira_pedidos
    add column if not exists itens_json text default '[]';

    create index if not exists idx_carteira_ativo_analista
    on carteira_pedidos (ativo, analista);

    create index if not exists idx_carteira_status
    on carteira_pedidos (status);

    create index if not exists idx_carteira_dt
    on carteira_pedidos (dt_agendada_ordem);

    create index if not exists idx_historico_doc
    on carteira_historico (doc_id);
    """

    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as e:
        st.error("Erro ao criar/verificar as tabelas no Neon.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


inicializar_banco()


def campos_sql(campos=None):
    if not campos:
        campos = CAMPOS_PEDIDOS.copy()
    else:
        campos = [c for c in campos if c in CAMPOS_PEDIDOS]

    if "doc_id" not in campos:
        campos = ["doc_id"] + campos

    return campos


def buscar_docs(ativos=None, analista=None, status=None, campos=None, tamanho_lote=5000):
    campos = campos_sql(campos)
    select_cols = ", ".join(campos)

    sql = f"""
        select {select_cols}
        from carteira_pedidos
        where 1 = 1
    """

    params = {}

    if ativos is not None:
        sql += " and ativo = :ativo"
        params["ativo"] = bool(ativos)

    if analista:
        sql += " and analista = :analista"
        params["analista"] = analista

    if status:
        sql += " and status = :status"
        params["status"] = status

    sql += """
        order by analista, departamento, dt_agendada_ordem, pedido
        limit :limite
    """
    params["limite"] = int(tamanho_lote)

    try:
        with engine.begin() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
            return [dict(r) for r in rows]
    except Exception as e:
        st.error("Não consegui consultar o Neon agora.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def buscar_docs_por_ids(doc_ids, campos=None, tamanho_lote=500):
    ids = list(dict.fromkeys(list(doc_ids)))

    if not ids:
        return []

    campos = campos_sql(campos)
    select_cols = ", ".join(campos)

    resultado = []

    sql = text(f"""
        select {select_cols}
        from carteira_pedidos
        where doc_id in :ids
    """).bindparams(bindparam("ids", expanding=True))

    try:
        with engine.begin() as conn:
            for i in range(0, len(ids), tamanho_lote):
                lote = ids[i:i + tamanho_lote]
                rows = conn.execute(sql, {"ids": lote}).mappings().all()
                resultado.extend([dict(r) for r in rows])

        return resultado

    except Exception as e:
        st.error("Não consegui buscar os pedidos no Neon.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def buscar_doc(doc_id):
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("select * from carteira_pedidos where doc_id = :doc_id"),
                {"doc_id": doc_id}
            ).mappings().first()

            return dict(row) if row else None

    except Exception as e:
        st.error("Erro ao buscar o pedido no Neon.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def historico_doc(doc_id):
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    select tipo, data, usuario, observacao, cobranca_numero, status_apos
                    from carteira_historico
                    where doc_id = :doc_id
                    order by data desc, id desc
                """),
                {"doc_id": doc_id}
            ).mappings().all()

            return [dict(r) for r in rows]

    except Exception as e:
        st.error("Erro ao carregar histórico.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def buscar_obs_ultima_cobranca(doc_ids):
    ids = list(dict.fromkeys([x for x in doc_ids if x]))

    if not ids:
        return {}

    sql = text("""
        select distinct on (h.doc_id)
            h.doc_id,
            h.observacao
        from carteira_historico h
        join carteira_pedidos p
          on p.doc_id = h.doc_id
        where h.doc_id in :ids
          and coalesce(h.observacao, '') <> ''
          and (
              (
                  p.status in ('ACIONAR COMPRADOR', 'COMPRADOR ACIONADO')
                  and h.tipo in ('NECESSARIO_ACIONAR_COMPRADOR', 'COMPRADOR_ACIONADO')
              )
              or (
                  p.status not in ('ACIONAR COMPRADOR', 'COMPRADOR ACIONADO')
                  and h.tipo = 'COBRANCA'
                  and h.cobranca_numero = p.cobrancas
              )
          )
        order by h.doc_id, h.data desc, h.id desc
    """).bindparams(bindparam("ids", expanding=True))

    try:
        with engine.begin() as conn:
            rows = conn.execute(sql, {"ids": ids}).mappings().all()

        return {
            r["doc_id"]: r.get("observacao", "")
            for r in rows
        }

    except Exception as e:
        st.error("Erro ao buscar observações de cobrança.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def buscar_data_cobranca_por_numero(doc_ids):
    ids = list(dict.fromkeys([x for x in doc_ids if x]))

    if not ids:
        return {}

    sql = text("""
        select distinct on (doc_id, cobranca_numero)
            doc_id,
            cobranca_numero,
            data
        from carteira_historico
        where doc_id in :ids
          and tipo = 'COBRANCA'
          and cobranca_numero is not null
        order by doc_id, cobranca_numero, data desc, id desc
    """).bindparams(bindparam("ids", expanding=True))

    try:
        with engine.begin() as conn:
            rows = conn.execute(sql, {"ids": ids}).mappings().all()

        mapa = {}

        for r in rows:
            doc_id = r["doc_id"]
            numero = int(r.get("cobranca_numero") or 0)
            mapa.setdefault(doc_id, {})[numero] = r.get("data", "")

        return mapa

    except Exception as e:
        st.error("Erro ao buscar datas das cobranças.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def montar_linha_banco(dados):
    linha = {}

    for campo in CAMPOS_PEDIDOS:
        linha[campo] = dados.get(campo)

    linha["saldo_cmv"] = float(linha.get("saldo_cmv") or 0)
    linha["pre_nota_cmv"] = float(linha.get("pre_nota_cmv") or 0)
    linha["nao_faturado_cmv"] = float(linha.get("nao_faturado_cmv") or 0)
    linha["qtd_itens"] = int(linha.get("qtd_itens") or 0)
    linha["ativo"] = bool(linha.get("ativo"))
    linha["cobrancas"] = int(linha.get("cobrancas") or 0)
    linha["comprador_acionado"] = bool(linha.get("comprador_acionado"))

    itens = linha.get("itens_json", [])

    if isinstance(itens, (list, dict)):
        linha["itens_json"] = json.dumps(itens, ensure_ascii=False)
    elif itens is None or str(itens).strip() == "":
        linha["itens_json"] = "[]"
    else:
        linha["itens_json"] = str(itens)

    for campo in CAMPOS_PEDIDOS:
        if linha[campo] is None:
            if campo in ["saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv"]:
                linha[campo] = 0
            elif campo in ["qtd_itens", "cobrancas"]:
                linha[campo] = 0
            elif campo in ["ativo", "comprador_acionado"]:
                linha[campo] = False
            elif campo == "itens_json":
                linha[campo] = "[]"
            else:
                linha[campo] = ""

    return linha


UPSERT_PEDIDO_SQL = text("""
    insert into carteira_pedidos (
        doc_id, pedido, analista, departamento, departamento_norm, fornecedor,
        dt_agendada, dt_agendada_ordem,
        saldo_cmv, pre_nota_cmv, nao_faturado_cmv, qtd_itens,
        ativo, status, cobrancas, comprador_acionado,
        ultima_cobranca, data_primeira_entrada, data_ultimo_upload,
        data_cancelamento, criado_em, atualizado_em, itens_json
    )
    values (
        :doc_id, :pedido, :analista, :departamento, :departamento_norm, :fornecedor,
        :dt_agendada, :dt_agendada_ordem,
        :saldo_cmv, :pre_nota_cmv, :nao_faturado_cmv, :qtd_itens,
        :ativo, :status, :cobrancas, :comprador_acionado,
        :ultima_cobranca, :data_primeira_entrada, :data_ultimo_upload,
        :data_cancelamento, :criado_em, :atualizado_em, :itens_json
    )
    on conflict (doc_id) do update set
        pedido = excluded.pedido,
        analista = excluded.analista,
        departamento = excluded.departamento,
        departamento_norm = excluded.departamento_norm,
        fornecedor = excluded.fornecedor,
        dt_agendada = excluded.dt_agendada,
        dt_agendada_ordem = excluded.dt_agendada_ordem,
        saldo_cmv = excluded.saldo_cmv,
        pre_nota_cmv = excluded.pre_nota_cmv,
        nao_faturado_cmv = excluded.nao_faturado_cmv,
        qtd_itens = excluded.qtd_itens,
        ativo = excluded.ativo,
        status = excluded.status,
        cobrancas = excluded.cobrancas,
        comprador_acionado = excluded.comprador_acionado,
        ultima_cobranca = excluded.ultima_cobranca,
        data_primeira_entrada = coalesce(carteira_pedidos.data_primeira_entrada, excluded.data_primeira_entrada),
        data_ultimo_upload = excluded.data_ultimo_upload,
        data_cancelamento = excluded.data_cancelamento,
        criado_em = coalesce(carteira_pedidos.criado_em, excluded.criado_em),
        atualizado_em = excluded.atualizado_em,
        itens_json = excluded.itens_json
""")


INSERT_HISTORICO_SQL = text("""
    insert into carteira_historico (
        doc_id, pedido, tipo, data, usuario, observacao, cobranca_numero, status_apos
    )
    values (
        :doc_id, :pedido, :tipo, :data, :usuario, :observacao, :cobranca_numero, :status_apos
    )
""")


UPDATE_INATIVO_SQL = text("""
    update carteira_pedidos
    set
        ativo = false,
        status = :status,
        data_cancelamento = coalesce(:data_cancelamento, data_cancelamento),
        atualizado_em = :atualizado_em
    where doc_id = :doc_id
""")


# =========================
# AÇÕES NO BANCO
# =========================
def registrar_cobranca_lote(doc_ids, usuario, observacao):
    ids = list(dict.fromkeys([x for x in doc_ids if x]))

    if not ids:
        st.warning("Selecione pelo menos um pedido.")
        return

    itens = buscar_docs_por_ids(
        ids,
        campos=[
            "doc_id",
            "pedido",
            "cobrancas",
            "comprador_acionado",
        ]
    )

    if not itens:
        st.error("Nenhum pedido encontrado para registrar cobrança.")
        return

    data_evento = agora_str()
    updates = []
    historicos = []

    for item in itens:
        doc_id = item["doc_id"]
        atual = int(item.get("cobrancas", 0) or 0)
        nova_qtd = atual + 1
        comprador_acionado = bool(item.get("comprador_acionado", False))
        novo_status = status_por_cobranca(nova_qtd, comprador_acionado)

        updates.append({
            "doc_id": doc_id,
            "cobrancas": nova_qtd,
            "status": novo_status,
            "ultima_cobranca": data_evento,
            "atualizado_em": data_evento,
        })

        historicos.append({
            "doc_id": doc_id,
            "pedido": item.get("pedido", ""),
            "tipo": "COBRANCA",
            "data": data_evento,
            "usuario": usuario,
            "observacao": observacao or "",
            "cobranca_numero": nova_qtd,
            "status_apos": novo_status,
        })

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    update carteira_pedidos
                    set
                        cobrancas = :cobrancas,
                        status = :status,
                        ultima_cobranca = :ultima_cobranca,
                        atualizado_em = :atualizado_em
                    where doc_id = :doc_id
                """),
                updates
            )

            conn.execute(INSERT_HISTORICO_SQL, historicos)

        try:
            st.cache_data.clear()
        except Exception:
            pass

    except Exception as e:
        st.error("Erro ao registrar cobrança.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def excluir_cobranca_selecionada_lote(doc_ids, usuario, observacao, cobranca_numero):
    ids = list(dict.fromkeys([x for x in doc_ids if x]))

    if not ids:
        st.warning("Selecione pelo menos um pedido.")
        return

    try:
        cobranca_numero = int(cobranca_numero)
    except Exception:
        st.warning("Selecione qual cobrança deseja excluir.")
        return

    if cobranca_numero <= 0:
        st.warning("Selecione qual cobrança deseja excluir.")
        return

    itens = buscar_docs_por_ids(
        ids,
        campos=[
            "doc_id",
            "pedido",
            "cobrancas",
            "comprador_acionado",
            "status",
        ]
    )

    if not itens:
        st.error("Nenhum pedido encontrado para excluir cobrança.")
        return

    datas_por_doc = buscar_data_cobranca_por_numero(ids)

    data_evento = agora_str()
    updates = []
    historicos = []
    ignorados = []

    for item in itens:
        doc_id = item["doc_id"]
        atual = int(item.get("cobrancas", 0) or 0)

        if atual < cobranca_numero:
            ignorados.append(item.get("pedido", doc_id))
            continue

        # Se excluir a 2ª cobrança, por exemplo, o pedido volta para 1 cobrança.
        # Isso evita ficar com histórico e status inconsistentes.
        nova_qtd = max(cobranca_numero - 1, 0)
        novo_status = status_por_cobranca(nova_qtd, False)
        nova_ultima = datas_por_doc.get(doc_id, {}).get(nova_qtd, "") if nova_qtd > 0 else ""

        updates.append({
            "doc_id": doc_id,
            "cobrancas": nova_qtd,
            "status": novo_status,
            "comprador_acionado": False,
            "ultima_cobranca": nova_ultima,
            "atualizado_em": data_evento,
        })

        historicos.append({
            "doc_id": doc_id,
            "pedido": item.get("pedido", ""),
            "tipo": "EXCLUSAO_COBRANCA",
            "data": data_evento,
            "usuario": usuario,
            "observacao": observacao or f"Exclusão da {cobranca_numero}ª cobrança. Pedido voltou para {nova_qtd} cobrança(s).",
            "cobranca_numero": cobranca_numero,
            "status_apos": novo_status,
        })

    if not updates:
        st.warning(f"Nenhum pedido tinha {cobranca_numero} cobrança(s) para excluir.")
        return

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    update carteira_pedidos
                    set
                        cobrancas = :cobrancas,
                        status = :status,
                        comprador_acionado = :comprador_acionado,
                        ultima_cobranca = :ultima_cobranca,
                        atualizado_em = :atualizado_em
                    where doc_id = :doc_id
                """),
                updates
            )

            conn.execute(INSERT_HISTORICO_SQL, historicos)

        try:
            st.cache_data.clear()
        except Exception:
            pass

        if ignorados:
            st.warning(
                f"Alguns pedidos foram ignorados porque não tinham {cobranca_numero} cobrança(s): "
                + ", ".join(str(x) for x in ignorados[:20])
            )

    except Exception as e:
        st.error("Erro ao excluir cobrança.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def sinalizar_acionar_comprador_lote(doc_ids, usuario, observacao):
    ids = list(dict.fromkeys([x for x in doc_ids if x]))

    if not ids:
        st.warning("Selecione pelo menos um pedido.")
        return

    itens = buscar_docs_por_ids(
        ids,
        campos=[
            "doc_id",
            "pedido",
            "cobrancas",
            "status",
        ]
    )

    if not itens:
        st.error("Nenhum pedido encontrado.")
        return

    data_evento = agora_str()
    updates = []
    historicos = []
    ignorados = []

    for item in itens:
        doc_id = item["doc_id"]
        cobrancas = int(item.get("cobrancas", 0) or 0)
        status_atual = item.get("status", "")

        if cobrancas < 3 and status_atual != STATUS_ACIONAR_COMPRADOR:
            ignorados.append(item.get("pedido", doc_id))
            continue

        updates.append({
            "doc_id": doc_id,
            "status": STATUS_ACIONAR_COMPRADOR,
            "atualizado_em": data_evento,
        })

        historicos.append({
            "doc_id": doc_id,
            "pedido": item.get("pedido", ""),
            "tipo": "NECESSARIO_ACIONAR_COMPRADOR",
            "data": data_evento,
            "usuario": usuario,
            "observacao": observacao or "Após 3 cobranças sem retorno, necessário acionar comprador.",
            "cobranca_numero": cobrancas,
            "status_apos": STATUS_ACIONAR_COMPRADOR,
        })

    if not updates:
        st.warning("Nenhum pedido estava com 3 cobranças para acionar comprador.")
        return

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    update carteira_pedidos
                    set
                        status = :status,
                        atualizado_em = :atualizado_em
                    where doc_id = :doc_id
                """),
                updates
            )

            conn.execute(INSERT_HISTORICO_SQL, historicos)

        try:
            st.cache_data.clear()
        except Exception:
            pass

        if ignorados:
            st.warning(
                "Pedidos ignorados porque ainda não têm 3 cobranças: "
                + ", ".join(str(x) for x in ignorados[:20])
            )

    except Exception as e:
        st.error("Erro ao sinalizar comprador.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


def marcar_comprador_acionado_lote(doc_ids, usuario, observacao):
    ids = list(dict.fromkeys([x for x in doc_ids if x]))

    if not ids:
        st.warning("Selecione pelo menos um pedido.")
        return

    itens = buscar_docs_por_ids(
        ids,
        campos=[
            "doc_id",
            "pedido",
        ]
    )

    if not itens:
        st.error("Nenhum pedido encontrado para marcar comprador acionado.")
        return

    data_evento = agora_str()

    updates = []
    historicos = []

    for item in itens:
        doc_id = item["doc_id"]

        updates.append({
            "doc_id": doc_id,
            "status": STATUS_COMPRADOR_ACIONADO,
            "atualizado_em": data_evento,
        })

        historicos.append({
            "doc_id": doc_id,
            "pedido": item.get("pedido", ""),
            "tipo": "COMPRADOR_ACIONADO",
            "data": data_evento,
            "usuario": usuario,
            "observacao": observacao or "",
            "cobranca_numero": None,
            "status_apos": STATUS_COMPRADOR_ACIONADO,
        })

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    update carteira_pedidos
                    set
                        comprador_acionado = true,
                        status = :status,
                        atualizado_em = :atualizado_em
                    where doc_id = :doc_id
                """),
                updates
            )

            conn.execute(INSERT_HISTORICO_SQL, historicos)

        try:
            st.cache_data.clear()
        except Exception:
            pass

    except Exception as e:
        st.error("Erro ao marcar comprador acionado.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()


# =========================
# LEITURA DO ARQUIVO
# =========================
def ler_arquivo(origem):
    nome = origem.name.lower()

    if nome.endswith(".csv"):
        conteudo = origem.getvalue()

        try:
            return pd.read_csv(io.BytesIO(conteudo), sep=None, engine="python")
        except Exception:
            return pd.read_csv(io.BytesIO(conteudo), sep=";")

    return pd.read_excel(origem)


def encontrar_coluna_fixa(df, nomes_possiveis):
    mapa = {norm(c): c for c in df.columns}

    for nome in nomes_possiveis:
        nome_n = norm(nome)

        if nome_n in mapa:
            return mapa[nome_n]

    for nome in nomes_possiveis:
        nome_n = norm(nome)

        for col_n, col_original in mapa.items():
            if nome_n in col_n or col_n in nome_n:
                return col_original

    return None



def encontrar_coluna_valor_cmv(df, tipo):
    """
    Encontra coluna de VALOR R$ / CMV, sem confundir com QTD.
    tipo: saldo | pre_nota | nao_faturado
    """
    mapa = {norm(c): c for c in df.columns}

    if tipo == "saldo":
        termos_obrigatorios = [["SALDO"]]
        termos_preferidos = ["CMV", "R"]
    elif tipo == "pre_nota":
        termos_obrigatorios = [["PRE", "NOTA"]]
        termos_preferidos = ["CMV", "R"]
    else:
        termos_obrigatorios = [["NAO", "FATURADO"], ["NAO", "FATUADO"], ["NAO", "FAT"]]
        termos_preferidos = ["CMV", "R"]

    def proibida(col_n):
        bloqueios = ["QTD", "QTDE", "QUANT", "QUANTIDADE", "DATA", "DT", "COD", "DESC"]
        return any(b in col_n for b in bloqueios)

    candidatos = []

    for col_n, col_original in mapa.items():
        if proibida(col_n):
            continue

        bate_tipo = False
        for grupo in termos_obrigatorios:
            if all(t in col_n for t in grupo):
                bate_tipo = True
                break

        if not bate_tipo:
            continue

        score = 0
        for pref in termos_preferidos:
            if pref in col_n:
                score += 10

        if "CMV" in col_n:
            score += 20
        if "R" in col_n:
            score += 8
        if "VALOR" in col_n:
            score += 8
        if "VLR" in col_n:
            score += 8

        candidatos.append((score, col_original))

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x[0], reverse=True)
    return candidatos[0][1]

def encontrar_colunas_itens(df):
    col_codigo = encontrar_coluna_fixa(df, [
        "Cod_Prod", "Cod Prod", "Código", "Codigo", "Cód", "Cod",
        "Cód Produto", "Cod Produto", "Código Produto", "Codigo Produto",
        "Cód. Produto", "Cod. Produto", "Código Item", "Codigo Item",
        "Cod Item", "Cód Item", "SKU", "Item", "Produto Código", "Produto Codigo",
        "Código Mercadoria", "Codigo Mercadoria", "Cod Mercadoria"
    ])

    col_descricao = encontrar_coluna_fixa(df, [
        "Desc_Prod", "Desc Prod", "Descrição", "Descricao", "Desc",
        "Descrição Produto", "Descricao Produto",
        "Produto", "Nome Produto", "Desc Produto", "Desc Item", "Mercadoria",
        "Descrição Item", "Descricao Item", "Descrição Mercadoria", "Descricao Mercadoria",
        "Nome Mercadoria", "Item Descrição", "Item Descricao"
    ])

    col_saldo_qtd = encontrar_coluna_fixa(df, [
        "Saldo QTD", "Saldo Quantidade", "Qtd", "QTD", "Quantidade", "Qtde", "Qt",
        "Qtd Pedida", "QTD Pedido"
    ])

    col_nao_faturado_qtd = encontrar_coluna_fixa(df, [
        "Não Faturado QTD", "Nao Faturado QTD", "Não Fatuado QTD", "Nao Fatuado QTD"
    ])

    col_pre_nota_qtd = encontrar_coluna_fixa(df, [
        "Pré-nota QTD", "Pre-nota QTD", "Pré-nota Qtd", "Pre-nota Qtd",
        "Pré Nota QTD", "Pre Nota QTD"
    ])

    mapa = {norm(c): c for c in df.columns}

    if not col_codigo:
        for col_n, col_original in mapa.items():
            if (
                ("COD PROD" in col_n or "COD" in col_n or "SKU" in col_n)
                and "BARRAS" not in col_n
                and "FABRICA" not in col_n
                and "FORNEC" not in col_n
                and "PEDIDO" not in col_n
                and "DEPART" not in col_n
            ):
                col_codigo = col_original
                break

    if not col_descricao:
        for col_n, col_original in mapa.items():
            if (
                ("DESC PROD" in col_n or "DESC" in col_n)
                and "DEPART" not in col_n
                and "FORNEC" not in col_n
            ):
                col_descricao = col_original
                break

    if not col_saldo_qtd:
        for col_n, col_original in mapa.items():
            if "SALDO QTD" in col_n:
                col_saldo_qtd = col_original
                break

    if not col_nao_faturado_qtd:
        for col_n, col_original in mapa.items():
            if "NAO FATURADO QTD" in col_n or "NAO FATUADO QTD" in col_n:
                col_nao_faturado_qtd = col_original
                break

    if not col_pre_nota_qtd:
        for col_n, col_original in mapa.items():
            if "PRE NOTA QTD" in col_n or "PRE NOTA QTD" in col_n:
                col_pre_nota_qtd = col_original
                break

    return {
        "codigo": col_codigo,
        "descricao": col_descricao,
        "qtd": col_saldo_qtd,
        "saldo_qtd": col_saldo_qtd,
        "nao_faturado_qtd": col_nao_faturado_qtd,
        "pre_nota_qtd": col_pre_nota_qtd,
    }


def montar_itens_do_pedido(grupo, colunas_itens, colunas_valores):
    itens = []

    col_codigo = colunas_itens.get("codigo")
    col_descricao = colunas_itens.get("descricao")
    col_qtd = colunas_itens.get("qtd")
    col_saldo_qtd = colunas_itens.get("saldo_qtd")
    col_nao_faturado_qtd = colunas_itens.get("nao_faturado_qtd")
    col_pre_nota_qtd = colunas_itens.get("pre_nota_qtd")

    col_saldo = colunas_valores.get("saldo_cmv")
    col_pre_nota = colunas_valores.get("pre_nota_cmv")
    col_nao_faturado = colunas_valores.get("nao_faturado_cmv")

    for _, linha in grupo.iterrows():
        codigo = ""
        descricao = ""
        qtd = 0
        saldo_qtd_item = 0
        nao_faturado_qtd_item = 0
        pre_nota_qtd_item = 0
        saldo_item = 0
        pre_nota_item = 0
        nao_faturado_item = 0

        if col_codigo and col_codigo in linha.index:
            codigo = str(linha.get(col_codigo, "") or "").strip()

        if col_descricao and col_descricao in linha.index:
            descricao = str(linha.get(col_descricao, "") or "").strip()

        if col_qtd and col_qtd in linha.index:
            qtd = converter_numero(linha.get(col_qtd, 0))

        if col_saldo_qtd and col_saldo_qtd in linha.index:
            saldo_qtd_item = converter_numero(linha.get(col_saldo_qtd, 0))

        if col_nao_faturado_qtd and col_nao_faturado_qtd in linha.index:
            nao_faturado_qtd_item = converter_numero(linha.get(col_nao_faturado_qtd, 0))

        if col_pre_nota_qtd and col_pre_nota_qtd in linha.index:
            pre_nota_qtd_item = converter_numero(linha.get(col_pre_nota_qtd, 0))

        if col_saldo and col_saldo in linha.index:
            saldo_item = converter_numero(linha.get(col_saldo, 0))

        if col_pre_nota and col_pre_nota in linha.index:
            pre_nota_item = converter_numero(linha.get(col_pre_nota, 0))

        if col_nao_faturado and col_nao_faturado in linha.index:
            nao_faturado_item = converter_numero(linha.get(col_nao_faturado, 0))

        if codigo or descricao or qtd or saldo_item or pre_nota_item or nao_faturado_item:
            itens.append({
                "codigo": codigo,
                "descricao": descricao,
                "qtd": qtd,
                "saldo_qtd_item": saldo_qtd_item,
                "nao_faturado_qtd_item": nao_faturado_qtd_item,
                "pre_nota_qtd_item": pre_nota_qtd_item,
                "saldo_cmv_item": saldo_item,
                "pre_nota_cmv_item": pre_nota_item,
                "nao_faturado_cmv_item": nao_faturado_item,
            })

    return itens


def mapear_colunas_fixas(df):
    col_pedido = encontrar_coluna_fixa(df, [
        "Pedido", "N Pedido", "Nº Pedido", "Num Pedido",
        "Número Pedido", "Numero Pedido", "OC", "Ordem"
    ])
    col_departamento = encontrar_coluna_fixa(df, [
        "Departamento", "Depto", "Setor"
    ])
    col_fornecedor = encontrar_coluna_fixa(df, [
        "Fornecedor", "Forneceor", "Razão Social", "Razao Social", "Vendor"
    ])
    col_data_prev = encontrar_coluna_fixa(df, [
        "Data Prev Entrega", "Data Prev. Entrega", "Dt Prev Entrega",
        "DT Prev Entrega", "Dt Prev Entr", "DT Prev Entr", "Prev Entrega",
        "Previsão Entrega", "Previsao Entrega", "Data Prevista Entrega",
        "Menor Data Prev Entrega"
    ])
    col_dt_agendamento = encontrar_coluna_fixa(df, [
        "DT Agendamento", "Dt Agendamento", "Data Agendamento",
        "Data Agendada", "DT Agendada", "Dt Agendada",
        "DT Agendando", "Dt Agendando", "Data Agendando",
        "Agendamento", "Agendada", "Agendando", "Dt Agend", "DT Agend"
    ])

    # Valores R$/CMV: procura sem confundir com colunas QTD.
    col_saldo = encontrar_coluna_valor_cmv(df, "saldo") or encontrar_coluna_fixa(df, [
        "Saldo R$ (CMV)", "Saldo R$(CMV)", "Saldo R CMV", "Saldo CMV",
        "Saldo R$", "Saldo Valor", "Valor Saldo", "Vlr Saldo"
    ])
    col_pre_nota = encontrar_coluna_valor_cmv(df, "pre_nota") or encontrar_coluna_fixa(df, [
        "Pré-nota R$ (CMV)", "Pre-nota R$ (CMV)",
        "Pré Nota R$ (CMV)", "Pre Nota R$ (CMV)",
        "Pré-Nota R$ (CMV)", "Pre-Nota R$ (CMV)",
        "Pré-nota R$(CMV)", "Pre-nota R$(CMV)",
        "Pré-nota CMV", "Pre-nota CMV", "Pré Nota CMV",
        "Pre Nota CMV", "Pré-Nota CMV", "Pre-Nota CMV", "Prenota CMV",
        "Pré-nota R$", "Pre-nota R$", "Pré Nota R$", "Pre Nota R$",
        "Pré-nota Valor", "Pre-nota Valor", "Valor Pré-nota", "Valor Pre-nota"
    ])
    col_nao_faturado = encontrar_coluna_valor_cmv(df, "nao_faturado") or encontrar_coluna_fixa(df, [
        "Não Faturado R$ (CMV)", "Nao Faturado R$ (CMV)",
        "Não Faturado R$(CMV)", "Nao Faturado R$(CMV)",
        "Não Faturado CMV", "Nao Faturado CMV",
        "Não Fatuado CMV", "Nao Fatuado CMV",
        "Nao Fat CMV", "Não Fat CMV",
        "Não Faturado R$", "Nao Faturado R$",
        "Não Faturado Valor", "Nao Faturado Valor",
        "Valor Não Faturado", "Valor Nao Faturado"
    ])

    colunas = {
        "pedido": col_pedido,
        "departamento": col_departamento,
        "fornecedor": col_fornecedor,
        "data_prev_entrega": col_data_prev,
        "dt_agendamento": col_dt_agendamento,
        "saldo_cmv": col_saldo,
        "pre_nota_cmv": col_pre_nota,
        "nao_faturado_cmv": col_nao_faturado,
    }

    faltando = [campo for campo, coluna in colunas.items() if coluna is None]

    return colunas, faltando


def agregar_por_pedido(df, colunas):
    base = df.copy()
    colunas_itens = encontrar_colunas_itens(df)

    base["_pedido"] = base[colunas["pedido"]].astype(str).str.strip()
    base["_departamento"] = base[colunas["departamento"]]
    base["_fornecedor"] = base[colunas["fornecedor"]]

    base["_data_prev_entrega"] = base[colunas["data_prev_entrega"]].apply(converter_data)
    base["_dt_agendamento"] = base[colunas["dt_agendamento"]].apply(converter_data)

    base["_saldo_cmv"] = base[colunas["saldo_cmv"]].apply(converter_numero)
    base["_pre_nota_cmv"] = base[colunas["pre_nota_cmv"]].apply(converter_numero)
    base["_nao_faturado_cmv"] = base[colunas["nao_faturado_cmv"]].apply(converter_numero)

    base = base[
        (base["_pedido"].notna()) &
        (base["_pedido"].astype(str).str.strip() != "") &
        (base["_pedido"].astype(str).str.lower() != "nan")
    ].copy()

    ids_arquivo_completo = set(
        hash_id(p)
        for p in base["_pedido"].astype(str).str.strip().unique()
    )

    total_itens_antes = len(base)

    base_sem_agendamento = base[
        base["_dt_agendamento"].isna()
    ].copy()

    retirados_agendamento = total_itens_antes - len(base_sem_agendamento)

    ids_sem_agendamento = set(
        hash_id(p)
        for p in base_sem_agendamento["_pedido"].astype(str).str.strip().unique()
    )

    if base_sem_agendamento.empty:
        agrupado = pd.DataFrame(columns=[
            "_pedido", "departamento", "fornecedor", "menor_data_prev_entrega",
            "saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv", "qtd_itens",
            "itens_json"
        ])

        agrupado.attrs["retirados_agendamento"] = retirados_agendamento
        agrupado.attrs["ids_arquivo_completo"] = ids_arquivo_completo
        agrupado.attrs["ids_sem_agendamento"] = ids_sem_agendamento

        return agrupado

    agrupado = base_sem_agendamento.groupby(
        "_pedido",
        dropna=False
    ).agg(
        departamento=("_departamento", primeiro_valor),
        fornecedor=("_fornecedor", primeiro_valor),
        menor_data_prev_entrega=("_data_prev_entrega", menor_data),
        saldo_cmv=("_saldo_cmv", "sum"),
        pre_nota_cmv=("_pre_nota_cmv", "sum"),
        nao_faturado_cmv=("_nao_faturado_cmv", "sum"),
        qtd_itens=("_pedido", "size")
    ).reset_index()

    itens_por_pedido = {}

    for pedido, grupo in base_sem_agendamento.groupby("_pedido", dropna=False):
        itens_por_pedido[pedido] = montar_itens_do_pedido(grupo, colunas_itens, colunas)

    agrupado["itens_json"] = agrupado["_pedido"].map(itens_por_pedido)

    agrupado.attrs["retirados_agendamento"] = retirados_agendamento
    agrupado.attrs["ids_arquivo_completo"] = ids_arquivo_completo
    agrupado.attrs["ids_sem_agendamento"] = ids_sem_agendamento

    return agrupado


def preparar_linhas(df):
    colunas, faltando = mapear_colunas_fixas(df)

    if faltando:
        return [], [], [
            "Colunas obrigatórias não encontradas: " + ", ".join(faltando)
        ], colunas, pd.DataFrame()

    agrupado = agregar_por_pedido(df, colunas)

    linhas_todas = []
    linhas_cobranca = []
    avisos = []
    limite = data_limite_cobranca()

    for _, row in agrupado.iterrows():
        pedido = str(row["_pedido"]).strip()
        departamento = str(row["departamento"]).strip()
        fornecedor = str(row["fornecedor"]).strip()
        dt_prev = row["menor_data_prev_entrega"]

        if not pedido or pedido.lower() == "nan":
            continue

        if not departamento or departamento.lower() == "nan":
            avisos.append(f"Pedido {pedido} sem departamento.")
            continue

        analista = identificar_analista(departamento)
        doc_id = hash_id(pedido)

        item = {
            "doc_id": doc_id,
            "pedido": pedido,
            "departamento": departamento,
            "departamento_norm": norm(departamento),
            "analista": analista,
            "fornecedor": fornecedor,
            "dt_agendada": data_br(dt_prev),
            "dt_agendada_ordem": dt_prev.isoformat() if dt_prev else "",
            "saldo_cmv": float(row["saldo_cmv"] or 0),
            "pre_nota_cmv": float(row["pre_nota_cmv"] or 0),
            "nao_faturado_cmv": float(row["nao_faturado_cmv"] or 0),
            "qtd_itens": int(row["qtd_itens"] or 0),
            "itens_json": row.get("itens_json", []),
        }

        linhas_todas.append(item)

        if dt_prev is None or pd.isna(dt_prev):
            avisos.append(
                f"Pedido {pedido} sem Data Prev Entrega válida. Não entrou na cobrança."
            )
            continue

        if dt_prev <= limite:
            linhas_cobranca.append(item)

    return linhas_todas, linhas_cobranca, avisos, colunas, agrupado


def processar_carteira(df, usuario):
    linhas_todas, linhas_cobranca, avisos, colunas, agrupado = preparar_linhas(df)

    if not linhas_todas and avisos:
        return {
            "erro": True,
            "avisos": avisos,
            "colunas": colunas,
        }

    ids_arquivo_completo = agrupado.attrs.get("ids_arquivo_completo", set())
    ids_sem_agendamento = agrupado.attrs.get("ids_sem_agendamento", set())

    ids_cobranca = {x["doc_id"] for x in linhas_cobranca}

    existentes_lista = buscar_docs_por_ids(
        ids_cobranca,
        campos=[
            "doc_id",
            "ativo",
            "status",
            "cobrancas",
            "comprador_acionado",
            "analista",
            "data_primeira_entrada",
            "criado_em",
            "ultima_cobranca",
        ]
    )

    existentes = {x["doc_id"]: x for x in existentes_lista}

    ativos_anteriores = buscar_docs(
        ativos=True,
        campos=["doc_id", "pedido", "analista"],
        tamanho_lote=5000
    )

    data_proc = agora_str()

    pedidos_para_salvar = []
    historicos = []
    inativos = []

    novos = 0
    reativados = 0
    mantidos = 0

    for item in linhas_cobranca:
        existente = existentes.get(item["doc_id"])

        if existente:
            qtd = int(existente.get("cobrancas", 0) or 0)
            comprador_acionado = bool(existente.get("comprador_acionado", False))
            status = status_por_cobranca(qtd, comprador_acionado)

            if existente.get("status") == STATUS_ACIONAR_COMPRADOR:
                status = STATUS_ACIONAR_COMPRADOR

            dados = {
                **item,
                "ativo": True,
                "status": status,
                "cobrancas": qtd,
                "comprador_acionado": comprador_acionado,
                "data_primeira_entrada": existente.get("data_primeira_entrada") or data_proc,
                "data_ultimo_upload": data_proc,
                "ultima_cobranca": existente.get("ultima_cobranca") or "",
                "data_cancelamento": "",
                "criado_em": existente.get("criado_em") or data_proc,
                "atualizado_em": data_proc,
            }

            if existente.get("ativo") is True:
                mantidos += 1
            else:
                reativados += 1

                historicos.append({
                    "doc_id": item["doc_id"],
                    "pedido": item["pedido"],
                    "tipo": "RETORNO_PARA_COBRANCA",
                    "data": data_proc,
                    "usuario": usuario,
                    "observacao": "Pedido voltou para cobrança por estar em atraso e sem DT Agendamento.",
                    "cobranca_numero": None,
                    "status_apos": status,
                })

            pedidos_para_salvar.append(montar_linha_banco(dados))

        else:
            novos += 1

            dados = {
                **item,
                "ativo": True,
                "status": STATUS_PENDENTE,
                "cobrancas": 0,
                "comprador_acionado": False,
                "data_primeira_entrada": data_proc,
                "data_ultimo_upload": data_proc,
                "ultima_cobranca": "",
                "data_cancelamento": "",
                "criado_em": data_proc,
                "atualizado_em": data_proc,
            }

            pedidos_para_salvar.append(montar_linha_banco(dados))

            historicos.append({
                "doc_id": item["doc_id"],
                "pedido": item["pedido"],
                "tipo": "ENTRADA_CARTEIRA",
                "data": data_proc,
                "usuario": usuario,
                "observacao": "Pedido entrou na carteira de cobrança por estar em atraso e sem DT Agendamento.",
                "cobranca_numero": None,
                "status_apos": STATUS_PENDENTE,
            })

    cancelados = 0
    fora_atraso = 0
    com_agendamento = 0

    for item in ativos_anteriores:
        doc_id = item["doc_id"]

        if doc_id in ids_cobranca:
            continue

        if doc_id not in ids_arquivo_completo:
            cancelados += 1
            status = ""
            obs = "Pedido saiu da carteira. Retirado da cobrança e da contagem."
            tipo = "SAIU_DA_CARTEIRA"
            data_cancelamento = None

        elif doc_id not in ids_sem_agendamento:
            com_agendamento += 1
            status = STATUS_COM_AGENDAMENTO
            obs = "Pedido está no arquivo, mas possui DT Agendamento preenchida. Retirado da cobrança."
            tipo = "COM_AGENDAMENTO"
            data_cancelamento = None

        else:
            fora_atraso += 1
            status = STATUS_FORA_ATRASO
            obs = "Pedido está sem DT Agendamento, mas não está em atraso pela menor Data Prev Entrega. Retirado da cobrança."
            tipo = "FORA_DO_ATRASO"
            data_cancelamento = None

        inativos.append({
            "doc_id": doc_id,
            "status": status,
            "data_cancelamento": data_cancelamento,
            "atualizado_em": data_proc,
        })

        historicos.append({
            "doc_id": doc_id,
            "pedido": item.get("pedido", ""),
            "tipo": tipo,
            "data": data_proc,
            "usuario": usuario,
            "observacao": obs,
            "cobranca_numero": None,
            "status_apos": status,
        })

    try:
        with engine.begin() as conn:
            if pedidos_para_salvar:
                conn.execute(UPSERT_PEDIDO_SQL, pedidos_para_salvar)

            if inativos:
                conn.execute(UPDATE_INATIVO_SQL, inativos)

            if historicos:
                conn.execute(INSERT_HISTORICO_SQL, historicos)

        try:
            st.cache_data.clear()
        except Exception:
            pass

    except Exception as e:
        st.error("Erro ao processar carteira no Neon.")
        with st.expander("Ver detalhe técnico"):
            st.code(repr(e))
        st.stop()

    return {
        "erro": False,
        "total_arquivo": len(ids_arquivo_completo),
        "sem_agendamento": len(ids_sem_agendamento),
        "em_atraso": len(linhas_cobranca),
        "retirados_por_data": len(linhas_todas) - len(linhas_cobranca),
        "retirados_agendamento": agrupado.attrs.get("retirados_agendamento", 0),
        "novos": novos,
        "mantidos": mantidos,
        "reativados": reativados,
        "cancelados": cancelados,
        "fora_atraso": fora_atraso,
        "com_agendamento": com_agendamento,
        "avisos": avisos,
        "colunas": colunas,
        "agrupado": agrupado,
    }


# =========================
# LOGIN
# =========================
def senha_valida(usuario, senha):
    if "app_passwords" in st.secrets:
        senhas = dict(st.secrets["app_passwords"])
        key = "admin" if usuario == "Admin" else usuario.lower()
        return senha == senhas.get(key, "")

    return senha == "1234"


def tela_login():
    st.title("Cobrança de Carteira")
    st.caption("Acompanhamento de pedidos atrasados.")

    with st.form("login"):
        usuario = st.selectbox("Usuário", ["Admin"] + list(ANALISTAS.keys()))
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)

    if entrar:
        if senha_valida(usuario, senha):
            st.session_state["logado"] = True
            st.session_state["usuario"] = usuario
            st.rerun()
        else:
            st.error("Senha incorreta.")


if "logado" not in st.session_state:
    st.session_state["logado"] = False

if not st.session_state["logado"]:
    tela_login()
    st.stop()

usuario_logado = st.session_state["usuario"]

# =========================
# SIDEBAR
# =========================
st.sidebar.title("Carteira")
st.sidebar.write(f"Usuário: **{usuario_logado}**")

if st.sidebar.button("Sair"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("Regra de cobrança")
st.sidebar.write(f"Hoje: **{data_br(hoje())}**")
st.sidebar.write(f"Cobrar até: **{data_br(data_limite_cobranca())}**")


# =========================
# TELAS
# =========================
def montar_df_itens(itens):
    if not itens:
        return pd.DataFrame()

    df = pd.DataFrame(itens)

    ordenar = [
        c for c in ["analista", "departamento", "dt_agendada_ordem", "status", "pedido"]
        if c in df.columns
    ]

    if ordenar:
        df = df.sort_values(ordenar, na_position="last")

    cols = [
        "analista", "departamento", "fornecedor", "pedido",
        "dt_agendada", "status", "cobrancas", "ultima_cobranca",
        "saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv",
        "qtd_itens", "dt_agendada_ordem", "doc_id"
    ]

    cols = [c for c in cols if c in df.columns]

    return df[cols]


def aplicar_filtros(df, pode_filtrar_analista=True, key_prefix=""):
    if df.empty:
        return df

    c1, c2, c3 = st.columns(3)

    with c1:
        if pode_filtrar_analista and "analista" in df.columns:
            analistas = ["TODOS"] + sorted(df["analista"].dropna().unique().tolist())
            f_analista = st.selectbox(
                "Analista",
                analistas,
                key=f"{key_prefix}_analista"
            )

            if f_analista != "TODOS":
                df = df[df["analista"] == f_analista]

    with c2:
        if "departamento" in df.columns:
            deps = ["TODOS"] + sorted(df["departamento"].dropna().unique().tolist())
            f_dep = st.selectbox(
                "Departamento",
                deps,
                key=f"{key_prefix}_departamento"
            )

            if f_dep != "TODOS":
                df = df[df["departamento"] == f_dep]

    with c3:
        if "status" in df.columns:
            sts = ["TODOS"] + sorted(df["status"].dropna().unique().tolist())
            f_status = st.selectbox(
                "Status",
                sts,
                key=f"{key_prefix}_status"
            )

            if f_status != "TODOS":
                df = df[df["status"] == f_status]

    busca = st.text_area(
        "Pesquisar pedido, fornecedor ou departamento",
        key=f"{key_prefix}_busca",
        height=80,
        placeholder="Pode colar vários pedidos separados por espaço, vírgula ou quebra de linha"
    )

    if busca:
        tokens = extrair_pedidos_texto(busca)

        if tokens:
            pedidos_normalizados = df["pedido"].apply(norm) if "pedido" in df.columns else pd.Series([], dtype=str)
            df_exato = df[pedidos_normalizados.isin(tokens)]

            if not df_exato.empty:
                df = df_exato
            else:
                def linha_match(linha):
                    pedido_n = norm(linha.get("pedido", ""))
                    texto_linha = norm(" ".join(str(v) for v in linha.values))

                    for token in tokens:
                        if token == pedido_n:
                            return True

                        if token in pedido_n:
                            return True

                        if token in texto_linha:
                            return True

                    return False

                df = df[df.apply(linha_match, axis=1)]

    return df


def metricas(df):
    if df.empty:
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        c1.metric("Ativos em atraso", 0)
        c2.metric("Saldo CMV", "R$ 0,00")
        c3.metric("Pré-nota CMV", "R$ 0,00")
        c4.metric("Não Faturado CMV", "R$ 0,00")
        c5.metric("Cobrado 3x", 0)
        c6.metric("Acionar comprador", 0)
        return

    total_saldo = df["saldo_cmv"].sum() if "saldo_cmv" in df.columns else 0
    total_pre_nota = df["pre_nota_cmv"].sum() if "pre_nota_cmv" in df.columns else 0
    total_nao_faturado = df["nao_faturado_cmv"].sum() if "nao_faturado_cmv" in df.columns else 0

    total_cobrado_3x = int((df["status"] == STATUS_COBRADO_3).sum()) if "status" in df.columns else 0
    total_acionar = int((df["status"] == STATUS_ACIONAR_COMPRADOR).sum()) if "status" in df.columns else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Ativos em atraso", len(df))
    c2.metric("Saldo CMV", formatar_moeda(total_saldo))
    c3.metric("Pré-nota CMV", formatar_moeda(total_pre_nota))
    c4.metric("Não Faturado CMV", formatar_moeda(total_nao_faturado))
    c5.metric("Cobrado 3x", total_cobrado_3x)
    c6.metric("Acionar comprador", total_acionar)

def configurar_colunas_e_processar(df, origem_texto):
    df.columns = [str(c).strip() for c in df.columns]

    st.info(
        f"Regra aplicada: primeiro retira produtos com **DT Agendamento preenchida**. "
        f"Depois considera somente pedidos sem agendamento com menor Data Prev Entrega até "
        f"**{data_br(data_limite_cobranca())}**."
    )

    st.subheader("Prévia do arquivo")
    st.caption(origem_texto)
    st.dataframe(df.head(30), use_container_width=True)

    linhas_todas, linhas_cobranca, avisos, colunas, agrupado = preparar_linhas(df)

    st.subheader("Colunas identificadas automaticamente")

    colunas_itens = encontrar_colunas_itens(df)

    colunas_df = pd.DataFrame([
        {"Campo usado": "Pedido", "Coluna encontrada": colunas.get("pedido")},
        {"Campo usado": "Departamento", "Coluna encontrada": colunas.get("departamento")},
        {"Campo usado": "Fornecedor", "Coluna encontrada": colunas.get("fornecedor")},
        {"Campo usado": "Data Prev Entrega", "Coluna encontrada": colunas.get("data_prev_entrega")},
        {"Campo usado": "DT Agendamento", "Coluna encontrada": colunas.get("dt_agendamento")},
        {"Campo usado": "Saldo CMV", "Coluna encontrada": colunas.get("saldo_cmv")},
        {"Campo usado": "Pré-nota CMV", "Coluna encontrada": colunas.get("pre_nota_cmv")},
        {"Campo usado": "Não Faturado CMV", "Coluna encontrada": colunas.get("nao_faturado_cmv")},
        {"Campo usado": "Código item", "Coluna encontrada": colunas_itens.get("codigo")},
        {"Campo usado": "Descrição item", "Coluna encontrada": colunas_itens.get("descricao")},
        {"Campo usado": "Saldo QTD item", "Coluna encontrada": colunas_itens.get("saldo_qtd")},
        {"Campo usado": "Não Faturado QTD item", "Coluna encontrada": colunas_itens.get("nao_faturado_qtd")},
        {"Campo usado": "Pré-nota QTD item", "Coluna encontrada": colunas_itens.get("pre_nota_qtd")},
    ])

    st.dataframe(colunas_df, use_container_width=True, hide_index=True)

    faltando = [k for k, v in colunas.items() if v is None]

    if faltando:
        st.error("Não consegui encontrar todas as colunas obrigatórias.")
        st.write("Campos faltando:")
        st.write(faltando)
        st.stop()

    preview_cobranca = pd.DataFrame(linhas_cobranca)

    st.subheader("Resumo antes de processar")

    total_saldo = sum(x["saldo_cmv"] for x in linhas_cobranca)
    total_pre_nota = sum(x["pre_nota_cmv"] for x in linhas_cobranca)
    total_nao_faturado = sum(x["nao_faturado_cmv"] for x in linhas_cobranca)

    retirados_agendamento = agrupado.attrs.get("retirados_agendamento", 0)
    ids_arquivo_completo = agrupado.attrs.get("ids_arquivo_completo", set())
    ids_sem_agendamento = agrupado.attrs.get("ids_sem_agendamento", set())

    c1, c2, c3 = st.columns(3)
    c1.metric("Pedidos no arquivo", len(ids_arquivo_completo))
    c2.metric("Pedidos sem agendamento", len(ids_sem_agendamento))
    c3.metric("Entram na cobrança", len(linhas_cobranca))

    c4, c5, c6 = st.columns(3)
    c4.metric("Itens retirados por DT Agendamento", retirados_agendamento)
    c5.metric("Fora por data", len(linhas_todas) - len(linhas_cobranca))
    c6.metric("Saldo CMV", formatar_moeda(total_saldo))

    c7, c8 = st.columns(2)
    c7.metric("Pré-nota CMV", formatar_moeda(total_pre_nota))
    c8.metric("Não Faturado CMV", formatar_moeda(total_nao_faturado))

    if not preview_cobranca.empty:
        st.subheader("Separação dos atrasados por analista")

        resumo = preview_cobranca.groupby(
            ["analista", "departamento"],
            dropna=False
        ).agg(
            pedidos=("pedido", "count"),
            saldo_cmv=("saldo_cmv", "sum"),
            pre_nota_cmv=("pre_nota_cmv", "sum"),
            nao_faturado_cmv=("nao_faturado_cmv", "sum")
        ).reset_index()

        st.dataframe(formatar_df_moeda(resumo), use_container_width=True, hide_index=True)

        sem_analista = preview_cobranca[preview_cobranca["analista"] == "SEM ANALISTA"]

        if not sem_analista.empty:
            st.warning("Existem departamentos em atraso sem analista. Confira a escrita do departamento.")
            st.dataframe(
                formatar_df_moeda(
                    sem_analista[[
                        "pedido", "departamento", "dt_agendada", "fornecedor",
                        "saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv"
                    ]].head(50)
                ),
                use_container_width=True,
                hide_index=True
            )

    with st.expander("Ver pedidos que entrarão na cobrança"):
        if preview_cobranca.empty:
            st.write("Nenhum pedido entra na cobrança pelo critério de data.")
        else:
            st.dataframe(
                formatar_df_moeda(preview_cobranca.head(300)),
                use_container_width=True,
                hide_index=True
            )

    if avisos:
        with st.expander("Avisos encontrados"):
            for a in avisos[:200]:
                st.write(a)

    confirmar = st.checkbox("Confirmo que esta é a carteira atualizada")

    if st.button(
        "Processar carteira",
        type="primary",
        use_container_width=True,
        disabled=not confirmar
    ):
        resultado = processar_carteira(df, usuario_logado)

        if resultado.get("erro"):
            st.error("Não foi possível processar a carteira.")
            for a in resultado.get("avisos", []):
                st.write(a)
            st.stop()

        st.success("Carteira processada com sucesso no Neon!")

        c1, c2, c3 = st.columns(3)
        c1.metric("Pedidos no arquivo", resultado["total_arquivo"])
        c2.metric("Pedidos sem agendamento", resultado["sem_agendamento"])
        c3.metric("Entraram na cobrança", resultado["em_atraso"])

        c4, c5, c6 = st.columns(3)
        c4.metric("Itens retirados por DT Agendamento", resultado["retirados_agendamento"])
        c5.metric("Fora por data", resultado["retirados_por_data"])
        c6.metric("Saíram da carteira", resultado["cancelados"])

        c7, c8, c9 = st.columns(3)
        c7.metric("Com agendamento", resultado["com_agendamento"])
        c8.metric("Fora do atraso", resultado["fora_atraso"])
        c9.metric("Novos", resultado["novos"])

        c10, c11 = st.columns(2)
        c10.metric("Mantidos", resultado["mantidos"])
        c11.metric("Reativados", resultado["reativados"])


def calcular_valores_item_exportacao(item):
    # IMPORTANTE: usa o valor R$/CMV real vindo da carteira.
    # Não faz rateio por QTD, porque isso joga Pré-nota para zero ou para Não Faturado.
    saldo_item = converter_numero(item.get("saldo_cmv_item", 0))
    pre_item = converter_numero(item.get("pre_nota_cmv_item", 0))
    nao_faturado_item = converter_numero(item.get("nao_faturado_cmv_item", 0))

    saldo_qtd = converter_numero(item.get("saldo_qtd_item", item.get("qtd", 0)))
    pre_qtd = converter_numero(item.get("pre_nota_qtd_item", 0))
    nao_faturado_qtd = converter_numero(item.get("nao_faturado_qtd_item", 0))

    return {
        "saldo_item": round(float(saldo_item), 2),
        "pre_item": round(float(pre_item), 2),
        "nao_faturado_item": round(float(nao_faturado_item), 2),
        "saldo_qtd": saldo_qtd,
        "pre_qtd": pre_qtd,
        "nao_faturado_qtd": nao_faturado_qtd,
    }


def montar_exportacao_acionar_comprador():
    pedidos = buscar_docs(
        ativos=True,
        status=STATUS_ACIONAR_COMPRADOR,
        campos=CAMPOS_PEDIDOS,
        tamanho_lote=10000
    )

    obs_por_doc = buscar_obs_ultima_cobranca([p.get("doc_id") for p in pedidos])

    linhas = []

    for pedido in pedidos:
        obs_cobranca = obs_por_doc.get(pedido.get("doc_id"), "")

        try:
            itens_pedido = json.loads(pedido.get("itens_json") or "[]")
        except Exception:
            itens_pedido = []

        linhas_pedido = []

        if not itens_pedido:
            saldo_pedido = converter_numero(pedido.get("saldo_cmv", 0))
            pre_pedido = converter_numero(pedido.get("pre_nota_cmv", 0))
            nao_faturado_pedido = converter_numero(pedido.get("nao_faturado_cmv", 0))

            linhas_pedido.append({
                "pedido": pedido.get("pedido", ""),
                "analista": pedido.get("analista", ""),
                "departamento": pedido.get("departamento", ""),
                "fornecedor": pedido.get("fornecedor", ""),
                "data_prev_entrega": pedido.get("dt_agendada", ""),
                "status": pedido.get("status", ""),
                "cobrancas": pedido.get("cobrancas", 0),
                "Obs Cobrança": obs_cobranca,
                "Cod_Prod": "",
                "Desc_Prod": "",
                "Saldo QTD": "",
                "Não Faturado QTD": "",
                "Pré-nota QTD": "",
                "Saldo R$ Item": saldo_pedido,
                "Pré-nota R$ Item": pre_pedido,
                "Não Faturado R$ Item": nao_faturado_pedido,
                "ultima_cobranca": pedido.get("ultima_cobranca", ""),
            })
        else:
            for item in itens_pedido:
                valores = calcular_valores_item_exportacao(item)

                linhas_pedido.append({
                    "pedido": pedido.get("pedido", ""),
                    "analista": pedido.get("analista", ""),
                    "departamento": pedido.get("departamento", ""),
                    "fornecedor": pedido.get("fornecedor", ""),
                    "data_prev_entrega": pedido.get("dt_agendada", ""),
                    "status": pedido.get("status", ""),
                    "cobrancas": pedido.get("cobrancas", 0),
                    "Obs Cobrança": obs_cobranca,
                    "Cod_Prod": item.get("codigo", ""),
                    "Desc_Prod": item.get("descricao", ""),
                    "Saldo QTD": valores["saldo_qtd"],
                    "Não Faturado QTD": valores["nao_faturado_qtd"],
                    "Pré-nota QTD": valores["pre_qtd"],
                    "Saldo R$ Item": valores["saldo_item"],
                    "Pré-nota R$ Item": valores["pre_item"],
                    "Não Faturado R$ Item": valores["nao_faturado_item"],
                    "ultima_cobranca": pedido.get("ultima_cobranca", ""),
                })

        # Totais do pedido vêm direto do banco, que é calculado a partir das colunas R$/CMV da carteira.
        # Não usa soma/rateio dos itens para não zerar Pré-nota quando há Pré-nota no pedido.
        saldo_pedido_calculado = converter_numero(pedido.get("saldo_cmv", 0))
        pre_pedido_calculado = converter_numero(pedido.get("pre_nota_cmv", 0))
        nao_faturado_pedido_calculado = converter_numero(pedido.get("nao_faturado_cmv", 0))

        # Se for um registro antigo sem total no pedido, aí sim usa a soma dos itens como plano B.
        if saldo_pedido_calculado <= 0:
            saldo_pedido_calculado = round(sum(converter_numero(l.get("Saldo R$ Item", 0)) for l in linhas_pedido), 2)

        if pre_pedido_calculado <= 0:
            pre_pedido_calculado = round(sum(converter_numero(l.get("Pré-nota R$ Item", 0)) for l in linhas_pedido), 2)

        if nao_faturado_pedido_calculado <= 0:
            nao_faturado_pedido_calculado = round(sum(converter_numero(l.get("Não Faturado R$ Item", 0)) for l in linhas_pedido), 2)

        for linha in linhas_pedido:
            linha["Saldo R$ Pedido"] = saldo_pedido_calculado
            linha["Pré-nota R$ Pedido"] = pre_pedido_calculado
            linha["Não Faturado R$ Pedido"] = nao_faturado_pedido_calculado
            linhas.append(linha)

    df = pd.DataFrame(linhas)

    if not df.empty:
        ordem = [
            "analista",
            "departamento",
            "fornecedor",
            "pedido",
            "data_prev_entrega",
            "status",
            "cobrancas",
            "Obs Cobrança",
            "ultima_cobranca",
            "Cod_Prod",
            "Desc_Prod",
            "Saldo QTD",
            "Não Faturado QTD",
            "Pré-nota QTD",
            "Saldo R$ Item",
            "Pré-nota R$ Item",
            "Não Faturado R$ Item",
            "Saldo R$ Pedido",
            "Pré-nota R$ Pedido",
            "Não Faturado R$ Pedido",
        ]

        df = df[[c for c in ordem if c in df.columns]]

        df = df.rename(columns={
            "analista": "Analista",
            "departamento": "Departamento",
            "fornecedor": "Fornecedor",
            "pedido": "Pedido",
            "data_prev_entrega": "Data Prev Entrega",
            "status": "Status",
            "cobrancas": "Cobranças",
            "ultima_cobranca": "Última Cobrança",
        })

    return df

def gerar_excel_bytes(df):
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Acionar Comprador")

    output.seek(0)
    return output.getvalue()


def tela_exportar_acionar_comprador():
    st.header("Exportar Acionar Comprador")

    df_export = montar_exportacao_acionar_comprador()

    if df_export.empty:
        st.info("Nenhum pedido com status ACIONAR COMPRADOR no momento.")
        return

    resumo_pedidos_export = (
        df_export.groupby("Pedido", dropna=False)
        .agg({
            "Saldo R$ Pedido": "first",
            "Pré-nota R$ Pedido": "first",
            "Não Faturado R$ Pedido": "first",
        })
        .reset_index()
    )

    total_saldo_pedido = (
        resumo_pedidos_export["Saldo R$ Pedido"].apply(converter_numero).sum()
        if "Saldo R$ Pedido" in resumo_pedidos_export.columns
        else 0
    )
    total_pre_nota_pedido = (
        resumo_pedidos_export["Pré-nota R$ Pedido"].apply(converter_numero).sum()
        if "Pré-nota R$ Pedido" in resumo_pedidos_export.columns
        else 0
    )
    total_nao_faturado_pedido = (
        resumo_pedidos_export["Não Faturado R$ Pedido"].apply(converter_numero).sum()
        if "Não Faturado R$ Pedido" in resumo_pedidos_export.columns
        else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Linhas de itens", len(df_export))
    c2.metric("Pedidos", df_export["Pedido"].nunique())
    c3.metric("Saldo CMV", formatar_moeda(total_saldo_pedido))
    c4.metric("Pré-nota CMV", formatar_moeda(total_pre_nota_pedido))
    c5.metric("Não Faturado CMV", formatar_moeda(total_nao_faturado_pedido))

    st.dataframe(
        formatar_df_moeda(df_export),
        use_container_width=True,
        hide_index=True,
        height=520
    )

    excel_bytes = gerar_excel_bytes(df_export)

    st.download_button(
        "Baixar Excel - Acionar Comprador",
        data=excel_bytes,
        file_name="acionar_comprador_itens.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )


def tela_upload():
    st.header("Atualizar carteira")
    arquivo = st.file_uploader("Arquivo da carteira", type=["xlsx", "xls", "csv"])

    if not arquivo:
        st.info("Envie o arquivo da carteira para atualizar a base.")
        return

    df = ler_arquivo(arquivo)
    configurar_colunas_e_processar(df, f"Origem: upload manual - {arquivo.name}")


def tela_carteira(analista=None):
    titulo = "Minha carteira em atraso" if analista else "Carteira geral em atraso"
    st.header(titulo)

    st.info(f"Data limite da cobrança hoje: **{data_br(data_limite_cobranca())}**")

    itens = buscar_docs(
        ativos=True,
        analista=analista,
        campos=CAMPOS_LISTAGEM,
        tamanho_lote=5000
    )

    df = montar_df_itens(itens)

    if not df.empty and "doc_id" in df.columns:
        obs_por_doc = buscar_obs_ultima_cobranca(df["doc_id"].dropna().tolist())
        df["obs_cobranca"] = df["doc_id"].map(obs_por_doc).fillna("")

    metricas(df)

    if df.empty:
        st.info("Nenhum pedido ativo em atraso encontrado para este usuário.")
        return

    df_filtrado = aplicar_filtros(
        df,
        pode_filtrar_analista=(analista is None),
        key_prefix="carteira_geral" if analista is None else f"carteira_{analista}"
    )

    st.subheader("Pedidos em atraso para cobrar")

    ordem_tela = [
        "analista", "departamento", "fornecedor", "pedido",
        "dt_agendada", "status", "cobrancas", "obs_cobranca", "ultima_cobranca",
        "saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv",
    ]

    df_tela = df_filtrado[[c for c in ordem_tela if c in df_filtrado.columns]].copy()

    df_tela = df_tela.rename(columns={
        "analista": "Analista",
        "departamento": "Departamento",
        "fornecedor": "Fornecedor",
        "pedido": "Pedido",
        "dt_agendada": "Data Prev Entrega",
        "status": "Status",
        "cobrancas": "Cobranças",
        "obs_cobranca": "Obs Cobrança",
        "ultima_cobranca": "Última Cobrança",
        "saldo_cmv": "Saldo CMV",
        "pre_nota_cmv": "Pré-nota CMV",
        "nao_faturado_cmv": "Não Faturado CMV",
    })

    st.dataframe(
        formatar_df_moeda(df_tela),
        use_container_width=True,
        hide_index=True,
        height=420
    )

    df_csv = df_tela.copy()
    df_csv = formatar_df_moeda(df_csv)

    csv = df_csv.to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        "Baixar carteira filtrada em CSV",
        data=csv,
        file_name="carteira_cobranca_atraso.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.divider()
    st.subheader("Registrar cobrança")

    if df_filtrado.empty:
        st.info("Nenhum pedido encontrado com os filtros.")
        return

    df_filtrado = df_filtrado.copy()

    df_filtrado["opcao_pedido"] = (
        df_filtrado["pedido"].astype(str)
        + " | "
        + df_filtrado["dt_agendada"].astype(str)
        + " | "
        + df_filtrado["departamento"].astype(str)
        + " | "
        + df_filtrado["fornecedor"].astype(str)
    )

    st.caption("Você pode selecionar vários pedidos abaixo ou colar vários pedidos, um por linha.")

    selecionados_opcoes = st.multiselect(
        "Selecione um ou mais pedidos",
        df_filtrado["opcao_pedido"].tolist(),
        key=f"pedidos_lote_{analista or 'geral'}"
    )

    pedidos_colados = st.text_area(
        "Ou cole vários pedidos para aplicar o mesmo retorno",
        key=f"pedidos_colados_{analista or 'geral'}",
        height=110,
        placeholder="Exemplo:\nLADPOD\nLAEQH2\nLADK55"
    )

    dfs_selecionados = []

    if selecionados_opcoes:
        dfs_selecionados.append(
            df_filtrado[df_filtrado["opcao_pedido"].isin(selecionados_opcoes)]
        )

    pedidos_digitados_norm = extrair_pedidos_texto(pedidos_colados)

    if pedidos_digitados_norm:
        pedidos_normalizados_df = df_filtrado["pedido"].apply(norm)

        df_digitados = df_filtrado[
            pedidos_normalizados_df.isin(pedidos_digitados_norm)
        ]

        dfs_selecionados.append(df_digitados)

        encontrados_norm = set(df_digitados["pedido"].apply(norm).tolist())
        nao_encontrados = [p for p in pedidos_digitados_norm if p not in encontrados_norm]

        with st.expander("Pedidos colados reconhecidos"):
            if pedidos_digitados_norm:
                st.code("\n".join(pedidos_digitados_norm))

        if nao_encontrados:
            st.warning(
                "Pedidos colados que não foram encontrados no filtro atual: "
                + ", ".join(nao_encontrados)
            )

    if dfs_selecionados:
        df_acao = pd.concat(dfs_selecionados, ignore_index=True)
        df_acao = df_acao.drop_duplicates(subset=["doc_id"])
    else:
        df_acao = pd.DataFrame()

    if df_acao.empty:
        st.info("Selecione ou cole os pedidos que receberão o mesmo retorno.")
        return

    st.success(f"{len(df_acao)} pedido(s) selecionado(s).")

    colunas_acao = [
        "analista",
        "departamento",
        "fornecedor",
        "pedido",
        "dt_agendada",
        "status",
        "cobrancas",
        "obs_cobranca",
        "ultima_cobranca",
        "saldo_cmv",
        "pre_nota_cmv",
        "nao_faturado_cmv",
    ]

    colunas_acao = [c for c in colunas_acao if c in df_acao.columns]

    df_acao_tela = df_acao[colunas_acao].copy()
    df_acao_tela = df_acao_tela.rename(columns={
        "analista": "Analista",
        "departamento": "Departamento",
        "fornecedor": "Fornecedor",
        "pedido": "Pedido",
        "dt_agendada": "Data Prev Entrega",
        "status": "Status",
        "cobrancas": "Cobranças",
        "obs_cobranca": "Obs Cobrança",
        "ultima_cobranca": "Última Cobrança",
        "saldo_cmv": "Saldo CMV",
        "pre_nota_cmv": "Pré-nota CMV",
        "nao_faturado_cmv": "Não Faturado CMV",
    })

    st.dataframe(
        formatar_df_moeda(df_acao_tela),
        use_container_width=True,
        hide_index=True,
        height=260
    )

    total_saldo = df_acao["saldo_cmv"].sum() if "saldo_cmv" in df_acao.columns else 0

    c1, c2 = st.columns(2)
    c1.metric("Pedidos selecionados", len(df_acao))
    c2.metric("Saldo CMV selecionado", formatar_moeda(total_saldo))

    obs = st.text_area(
        "Observação da cobrança",
        key=f"obs_lote_{analista or 'geral'}",
        placeholder="Ex.: cobrado representante X referente às fábricas/pedidos selecionados..."
    )

    maior_cobranca_selecionada = 0

    if "cobrancas" in df_acao.columns and not df_acao.empty:
        maior_cobranca_selecionada = int(df_acao["cobrancas"].fillna(0).astype(int).max())

    opcoes_excluir = [
        (1, "1ª cobrança"),
        (2, "2ª cobrança"),
        (3, "3ª cobrança"),
    ]
    opcoes_excluir = [op for op in opcoes_excluir if op[0] <= maior_cobranca_selecionada]

    if opcoes_excluir:
        label_para_numero = {label: numero for numero, label in opcoes_excluir}
        cobranca_excluir_label = st.selectbox(
            "Qual cobrança deseja excluir?",
            list(label_para_numero.keys()),
            key=f"cobranca_excluir_{analista or 'geral'}"
        )
        cobranca_excluir_numero = label_para_numero[cobranca_excluir_label]
        st.caption(
            f"Ao excluir a {cobranca_excluir_label}, o pedido volta para "
            f"{max(cobranca_excluir_numero - 1, 0)} cobrança(s)."
        )
    else:
        cobranca_excluir_numero = None

    doc_ids = df_acao["doc_id"].dropna().tolist()

    col_a, col_b, col_c, col_d = st.columns(4)

    tem_3_cobrancas = False
    tem_menos_de_2 = False
    tem_acionar = False
    tem_cobranca_para_excluir = False

    for _, linha in df_acao.iterrows():
        cobrancas = int(linha.get("cobrancas", 0) or 0)
        status_linha = linha.get("status", "")

        if cobrancas >= 3:
            tem_3_cobrancas = True

        if cobrancas < 3:
            tem_menos_de_2 = True

        if status_linha == STATUS_ACIONAR_COMPRADOR:
            tem_acionar = True

        if cobrancas > 0:
            tem_cobranca_para_excluir = True

    with col_a:
        if st.button(
            "Registrar cobrança",
            key=f"cobrar_lote_{analista or 'geral'}",
            use_container_width=True,
            disabled=not tem_menos_de_2
        ):
            doc_ids_cobranca = df_acao[
                df_acao["cobrancas"].fillna(0).astype(int) < 3
            ]["doc_id"].dropna().tolist()

            registrar_cobranca_lote(doc_ids_cobranca, usuario_logado, obs)
            st.success(f"Cobrança registrada para {len(doc_ids_cobranca)} pedido(s).")
            st.rerun()

    with col_b:
        if st.button(
            "Necessário acionar comprador",
            key=f"necessario_comprador_lote_{analista or 'geral'}",
            use_container_width=True,
            disabled=not tem_3_cobrancas
        ):
            doc_ids_comprador = df_acao[
                df_acao["cobrancas"].fillna(0).astype(int) >= 3
            ]["doc_id"].dropna().tolist()

            sinalizar_acionar_comprador_lote(doc_ids_comprador, usuario_logado, obs)
            st.success("Pedidos sinalizados para acionar comprador.")
            st.rerun()

    with col_c:
        if st.button(
            "Comprador acionado",
            key=f"comprador_lote_{analista or 'geral'}",
            use_container_width=True,
            disabled=not tem_acionar
        ):
            doc_ids_acionar = df_acao[
                df_acao["status"] == STATUS_ACIONAR_COMPRADOR
            ]["doc_id"].dropna().tolist()

            marcar_comprador_acionado_lote(doc_ids_acionar, usuario_logado, obs)
            st.success(f"Comprador acionado registrado para {len(doc_ids_acionar)} pedido(s).")
            st.rerun()

    with col_d:
        if st.button(
            "Excluir cobrança selecionada",
            key=f"excluir_cobranca_lote_{analista or 'geral'}",
            use_container_width=True,
            disabled=(not tem_cobranca_para_excluir or cobranca_excluir_numero is None)
        ):
            excluir_cobranca_selecionada_lote(
                doc_ids,
                usuario_logado,
                obs,
                cobranca_excluir_numero
            )
            st.success("Cobrança selecionada excluída dos pedidos quando aplicável.")
            st.rerun()

    if len(df_acao) == 1:
        doc_id_unico = df_acao.iloc[0]["doc_id"]

        if st.button("Carregar histórico do pedido selecionado", key=f"historico_{doc_id_unico}"):
            historico = historico_doc(doc_id_unico)

            if historico:
                hist_df = pd.DataFrame(historico)
                st.caption("Histórico")
                st.dataframe(hist_df, use_container_width=True, hide_index=True)
            else:
                st.info("Sem histórico para este pedido.")


def tela_fora_atraso():
    st.header("📅 Fora do atraso")

    itens = buscar_docs(
        ativos=False,
        status=STATUS_FORA_ATRASO,
        campos=CAMPOS_LISTAGEM,
        tamanho_lote=5000
    )

    df = montar_df_itens(itens)

    if df.empty:
        st.info("Nenhum pedido fora do atraso.")
        return

    df_filtrado = aplicar_filtros(df, pode_filtrar_analista=True, key_prefix="fora_atraso")

    st.metric("Fora do atraso", len(df_filtrado))

    df_tela = df_filtrado.drop(
        columns=["doc_id", "dt_agendada_ordem", "qtd_itens"],
        errors="ignore"
    )

    df_tela = df_tela.rename(columns={
        "dt_agendada": "data_prev_entrega",
    })

    st.dataframe(
        formatar_df_moeda(df_tela),
        use_container_width=True,
        hide_index=True,
        height=520
    )


def tela_cancelados():
    st.header("🚫 Retirados da conta")

    itens = buscar_docs(
        ativos=False,
        status=STATUS_CANCELADO,
        campos=CAMPOS_LISTAGEM,
        tamanho_lote=5000
    )

    df = montar_df_itens(itens)

    if df.empty:
        st.info("Nenhum pedido retirado da conta.")
        return

    df_filtrado = aplicar_filtros(df, pode_filtrar_analista=True, key_prefix="cancelados")

    st.metric("Retirados da conta", len(df_filtrado))

    df_tela = df_filtrado.drop(
        columns=["doc_id", "dt_agendada_ordem", "qtd_itens"],
        errors="ignore"
    )

    df_tela = df_tela.rename(columns={
        "dt_agendada": "data_prev_entrega",
    })

    st.dataframe(
        formatar_df_moeda(df_tela),
        use_container_width=True,
        hide_index=True,
        height=520
    )


def tela_regras():
    st.header("⚙️ Regras e departamentos")

    st.subheader("Regra da cobrança")
    st.write("1. Primeiro o sistema remove produtos que possuem DT Agendamento preenchida.")
    st.write("2. Só ficam produtos sem DT Agendamento.")
    st.write(f"3. Depois, cobra somente pedidos com menor Data Prev Entrega até {data_br(data_limite_cobranca())}.")
    st.write("4. Se o pedido tiver vários itens sem agendamento, o sistema usa a menor Data Prev Entrega.")
    st.write("5. Se o pedido sumir do arquivo completo, ele será retirado da cobrança e da contagem.")
    st.write("6. Não existe regra de marcar como entregue.")

    st.subheader("Fluxo de cobrança")
    st.write("1. Pedido atrasado entra como PENDENTE.")
    st.write("2. Registrar cobrança uma vez: status COBRADO 1X.")
    st.write("3. Registrar cobrança duas vezes: status COBRADO 2X.")
    st.write("4. Registrar cobrança três vezes: status COBRADO 3X.")
    st.write("5. Se cobrou 3x e não respondeu, clicar em NECESSÁRIO ACIONAR COMPRADOR.")
    st.write("6. Depois que falar com o comprador, clicar em COMPRADOR ACIONADO.")

    st.subheader("Valores considerados")
    st.write("Saldo CMV = Pré-nota CMV + Não Faturado CMV.")
    st.write("Os valores são considerados apenas dos produtos que ficaram sem DT Agendamento.")

    st.subheader("Analistas")

    for analista, deps in ANALISTAS.items():
        st.markdown(f"**{analista}**: {', '.join(deps)}")


# =========================
# ROTEAMENTO
# =========================
st.title("Cobrança de Carteira")
st.caption("Controle de pedidos atrasados.")

if usuario_logado == "Admin":
    pagina = st.radio(
        "Menu",
        ["Atualizar", "Carteira Geral", "Exportar Comprador", "Regras"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if pagina == "Atualizar":
        tela_upload()

    elif pagina == "Carteira Geral":
        tela_carteira()

    elif pagina == "Exportar Comprador":
        tela_exportar_acionar_comprador()

    elif pagina == "Regras":
        tela_regras()

else:
    pagina = st.radio(
        "Menu",
        ["Minha Carteira", "Regras"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if pagina == "Minha Carteira":
        tela_carteira(usuario_logado)

    elif pagina == "Regras":
        tela_regras()
