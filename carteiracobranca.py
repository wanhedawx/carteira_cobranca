import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import ArrayUnion
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unicodedata import normalize
import hashlib
import io

# =========================
# CONFIGURAÇÕES
# =========================
st.set_page_config(
    page_title="Cobrança de Carteira",
    page_icon="📋",
    layout="wide"
)

TZ = ZoneInfo("America/Maceio")
COLLECTION = "carteira_cobranca"

ANALISTAS = {
    "Cleviton": [
        "Portas e Janelas", "Ferramentas", "Ferragens", "Automotivos"
    ],
    "Alec": [
        "Eletrica", "Elétrica", "Hidraulica", "Hidráulica", "Iluminação", "Iluminacao"
    ],
    "Jonatas": [
        "Moveis e Colchoes", "Decoração", "Móveis e Decoração", "Cama Mesa e Banho", "Lazer",
        "Casa e UD e Jardim", "Casa UD e Jardim", "Casa e Jardim", "Utilidades Domésticas"
    ],
    "Beatriz": [
        "Eletro", "Tecnologia", "Climatização", "Climatizacao"
    ],
    "Ruan": [
        "Tintas", "Organização da Casa", "Organizacao da Casa"
    ],
    "Jessica": [
        "Materiais de Construção", "Materias de Construçao", "Materiais de Construcao",
        "Banho e Cozinha"
    ],
    "Rose": [
        "Pisos e revestimento"    
    ],
}

STATUS_PENDENTE = "PENDENTE"
STATUS_COBRADO_1 = "COBRADO 1X"
STATUS_COBRADO_2 = "COBRADO 2X"
STATUS_ACIONAR_COMPRADOR = "ACIONAR COMPRADOR"
STATUS_COMPRADOR_ACIONADO = "COMPRADOR ACIONADO"
STATUS_FORA_ATRASO = "FORA DO ATRASO"
STATUS_CANCELADO = "CANCELADO / RETIRADO"

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
            return "-"

        v = float(valor)

        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor or "-")


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

    return STATUS_ACIONAR_COMPRADOR


def classe_status(status):
    if status == STATUS_PENDENTE:
        return "pendente"

    if status == STATUS_COBRADO_1:
        return "ok1"

    if status == STATUS_COBRADO_2:
        return "ok2"

    if status == STATUS_ACIONAR_COMPRADOR:
        return "comprador"

    if status == STATUS_COMPRADOR_ACIONADO:
        return "acionado"

    if status == STATUS_FORA_ATRASO:
        return "fora"

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

# =========================
# FIREBASE
# =========================
@st.cache_resource
def conectar_firestore():
    if not firebase_admin._apps:
        if "firebase" not in st.secrets:
            st.error("Firebase não configurado. Coloque as credenciais em Secrets do Streamlit.")
            st.stop()

        cred_dict = dict(st.secrets["firebase"])

        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")

        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    return firestore.client()


db = conectar_firestore()


def salvar_em_lotes(operacoes):
    batch = db.batch()
    contador = 0

    for op, ref, dados, merge in operacoes:
        if op == "set":
            batch.set(ref, dados, merge=bool(merge))
        elif op == "update":
            batch.update(ref, dados)

        contador += 1

        if contador >= 450:
            batch.commit()
            batch = db.batch()
            contador = 0

    if contador:
        batch.commit()


def buscar_docs(ativos=None):
    col = db.collection(COLLECTION)

    if ativos is True:
        docs = col.where("ativo", "==", True).stream()
    elif ativos is False:
        docs = col.where("ativo", "==", False).stream()
    else:
        docs = col.stream()

    linhas = []

    for d in docs:
        item = d.to_dict()
        item["doc_id"] = d.id
        linhas.append(item)

    return linhas


def buscar_doc(doc_id):
    ref = db.collection(COLLECTION).document(doc_id)
    snap = ref.get()

    if not snap.exists:
        return None

    dados = snap.to_dict()
    dados["doc_id"] = snap.id

    return dados


def registrar_cobranca(doc_id, usuario, observacao):
    item = buscar_doc(doc_id)

    if not item:
        st.error("Pedido não encontrado.")
        return

    atual = int(item.get("cobrancas", 0) or 0)
    nova_qtd = atual + 1
    comprador_acionado = bool(item.get("comprador_acionado", False))
    novo_status = status_por_cobranca(nova_qtd, comprador_acionado)

    evento = {
        "tipo": "COBRANCA",
        "data": agora_str(),
        "usuario": usuario,
        "observacao": observacao or "",
        "cobranca_numero": nova_qtd,
        "status_apos": novo_status,
    }

    db.collection(COLLECTION).document(doc_id).update({
        "cobrancas": nova_qtd,
        "status": novo_status,
        "ultima_cobranca": agora_str(),
        "historico": ArrayUnion([evento])
    })


def marcar_comprador_acionado(doc_id, usuario, observacao):
    evento = {
        "tipo": "COMPRADOR_ACIONADO",
        "data": agora_str(),
        "usuario": usuario,
        "observacao": observacao or "",
    }

    db.collection(COLLECTION).document(doc_id).update({
        "comprador_acionado": True,
        "status": STATUS_COMPRADOR_ACIONADO,
        "data_comprador_acionado": agora_str(),
        "historico": ArrayUnion([evento])
    })

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


def mapear_colunas_fixas(df):
    colunas = {
        "pedido": encontrar_coluna_fixa(df, [
            "Pedido",
            "N Pedido",
            "Nº Pedido",
            "Num Pedido",
            "Número Pedido",
            "Numero Pedido",
            "OC",
            "Ordem"
        ]),
        "departamento": encontrar_coluna_fixa(df, [
            "Departamento",
            "Depto",
            "Setor"
        ]),
        "fornecedor": encontrar_coluna_fixa(df, [
            "Fornecedor",
            "Forneceor",
            "Razão Social",
            "Razao Social",
            "Vendor"
        ]),
        "data_prev_entrega": encontrar_coluna_fixa(df, [
            "Data Prev Entrega",
            "Data Prev. Entrega",
            "Dt Prev Entrega",
            "DT Prev Entrega",
            "Prev Entrega",
            "Previsão Entrega",
            "Previsao Entrega",
            "Data Prevista Entrega",
            "Menor Data Prev Entrega"
        ]),
        "saldo_cmv": encontrar_coluna_fixa(df, [
            "Saldo R$ (CMV)",
            "Saldo CMV",
            "Saldo R CMV"
        ]),
        "pre_nota_cmv": encontrar_coluna_fixa(df, [
            "Pré-Nota R$ (CMV)",
            "Pre-Nota R$ (CMV)",
            "Pré-Nota CMV",
            "Pre-Nota CMV",
            "Prenota CMV",
            "Pré-Nota CMV",
            "Pre-Nota CMV"
        ]),
        "nao_faturado_cmv": encontrar_coluna_fixa(df, [
            "Não Faturado R$ (CMV)",
            "Nao Faturado R$ (CMV)",
            "Não Faturado CMV",
            "Nao Faturado CMV",
            "Não Fatuado CMV",
            "Nao Fatuado CMV",
            "Nao Fat CMV",
            "Não Fat CMV"
        ]),
    }

    faltando = [campo for campo, coluna in colunas.items() if coluna is None]

    return colunas, faltando


def agregar_por_pedido(df, colunas):
    base = df.copy()

    base["_pedido"] = base[colunas["pedido"]].astype(str).str.strip()
    base["_departamento"] = base[colunas["departamento"]]
    base["_fornecedor"] = base[colunas["fornecedor"]]

    base["_data_prev_entrega"] = base[colunas["data_prev_entrega"]].apply(converter_data)

    base["_saldo_cmv"] = base[colunas["saldo_cmv"]].apply(converter_numero)
    base["_pre_nota_cmv"] = base[colunas["pre_nota_cmv"]].apply(converter_numero)
    base["_nao_faturado_cmv"] = base[colunas["nao_faturado_cmv"]].apply(converter_numero)

    base = base[
        (base["_pedido"].notna()) &
        (base["_pedido"].astype(str).str.strip() != "") &
        (base["_pedido"].astype(str).str.lower() != "nan")
    ].copy()

    agrupado = base.groupby(
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

    agrupado["valor_total_cmv"] = (
        agrupado["saldo_cmv"] +
        agrupado["pre_nota_cmv"] +
        agrupado["nao_faturado_cmv"]
    )

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
            "valor_total_cmv": float(row["valor_total_cmv"] or 0),
            "qtd_itens": int(row["qtd_itens"] or 0),
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

    ids_arquivo = {x["doc_id"] for x in linhas_todas}
    ids_cobranca = {x["doc_id"] for x in linhas_cobranca}

    existentes_lista = buscar_docs()
    existentes = {x["doc_id"]: x for x in existentes_lista}
    ativos_anteriores = [x for x in existentes_lista if x.get("ativo") is True]

    data_proc = agora_str()
    operacoes = []

    novos = 0
    reativados = 0
    mantidos = 0

    for item in linhas_cobranca:
        ref = db.collection(COLLECTION).document(item["doc_id"])
        existente = existentes.get(item["doc_id"])

        if existente:
            qtd = int(existente.get("cobrancas", 0) or 0)
            comprador_acionado = bool(existente.get("comprador_acionado", False))
            status = status_por_cobranca(qtd, comprador_acionado)

            dados = {
                **item,
                "ativo": True,
                "status": status,
                "cobrancas": qtd,
                "comprador_acionado": comprador_acionado,
                "data_ultimo_upload": data_proc,
                "atualizado_em": data_proc,
            }

            if existente.get("ativo") is True:
                mantidos += 1
            else:
                reativados += 1
                dados["historico"] = ArrayUnion([{
                    "tipo": "RETORNO_PARA_COBRANCA",
                    "data": data_proc,
                    "usuario": usuario,
                    "observacao": "Pedido voltou para cobrança por estar em atraso até a data limite."
                }])

            operacoes.append(("set", ref, dados, True))

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
                "historico": [{
                    "tipo": "ENTRADA_CARTEIRA",
                    "data": data_proc,
                    "usuario": usuario,
                    "observacao": "Pedido entrou na carteira de cobrança por atraso."
                }]
            }

            operacoes.append(("set", ref, dados, True))

    cancelados = 0
    fora_atraso = 0

    for item in ativos_anteriores:
        doc_id = item["doc_id"]

        if doc_id in ids_cobranca:
            continue

        ref = db.collection(COLLECTION).document(doc_id)

        if doc_id not in ids_arquivo:
            cancelados += 1

            evento = {
                "tipo": "CANCELADO_RETIRADO",
                "data": data_proc,
                "usuario": usuario,
                "observacao": "Pedido saiu do arquivo completo. Retirado da cobrança e da contagem."
            }

            dados = {
                "ativo": False,
                "status": STATUS_CANCELADO,
                "data_cancelamento": data_proc,
                "atualizado_em": data_proc,
                "historico": ArrayUnion([evento])
            }

            operacoes.append(("update", ref, dados, None))

        else:
            fora_atraso += 1

            evento = {
                "tipo": "FORA_DO_ATRASO",
                "data": data_proc,
                "usuario": usuario,
                "observacao": "Pedido ainda está no arquivo, mas não está em atraso pela menor Data Prev Entrega. Retirado da cobrança."
            }

            dados = {
                "ativo": False,
                "status": STATUS_FORA_ATRASO,
                "atualizado_em": data_proc,
                "historico": ArrayUnion([evento])
            }

            operacoes.append(("update", ref, dados, None))

    salvar_em_lotes(operacoes)

    return {
        "erro": False,
        "total_arquivo": len(linhas_todas),
        "em_atraso": len(linhas_cobranca),
        "retirados_por_data": len(linhas_todas) - len(linhas_cobranca),
        "novos": novos,
        "mantidos": mantidos,
        "reativados": reativados,
        "cancelados": cancelados,
        "fora_atraso": fora_atraso,
        "avisos": avisos,
        "colunas": colunas,
        "agrupado": agrupado,
    }

# =========================
# LOGIN
# =========================
def senha_valida(usuario, senha):
    if "app_passwords" in st.secrets:
        key = "admin" if usuario == "Admin" else usuario.lower()
        return senha == st.secrets["app_passwords"].get(key, "")

    return senha == "1234"


def tela_login():
    st.title("📋 Cobrança de Carteira")
    st.caption("Acompanhamento de pedidos atrasados por analista, departamento e cobrança.")

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
st.sidebar.title("📋 Carteira")
st.sidebar.write(f"Usuário: **{usuario_logado}**")

if st.sidebar.button("Sair"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("Regra de atraso")
st.sidebar.write(f"Hoje: **{data_br(hoje())}**")
st.sidebar.write(f"Cobrar até: **{data_br(data_limite_cobranca())}**")
st.sidebar.write("Usa a menor Data Prev Entrega do pedido.")
st.sidebar.write("Pedido que sumiu do arquivo sai da conta.")

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
        "pedido", "analista", "departamento", "fornecedor",
        "dt_agendada", "qtd_itens",
        "saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv", "valor_total_cmv",
        "status", "cobrancas", "ultima_cobranca",
        "data_primeira_entrada", "data_ultimo_upload", "data_cancelamento", "doc_id"
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

    busca = st.text_input(
        "Pesquisar pedido, fornecedor ou departamento",
        key=f"{key_prefix}_busca"
    )

    if busca:
        busca_n = norm(busca)
        mask = df.apply(
            lambda linha: busca_n in norm(" ".join(str(v) for v in linha.values)),
            axis=1
        )
        df = df[mask]

    return df


def metricas(df):
    if df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ativos em atraso", 0)
        c2.metric("Valor total CMV", "R$ 0,00")
        c3.metric("Cobrado 2x", 0)
        c4.metric("Acionar comprador", 0)
        return

    total = df["valor_total_cmv"].sum() if "valor_total_cmv" in df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ativos em atraso", len(df))
    c2.metric("Valor total CMV", formatar_moeda(total))
    c3.metric("Cobrado 2x", int((df["status"] == STATUS_COBRADO_2).sum()))
    c4.metric("Acionar comprador", int((df["status"] == STATUS_ACIONAR_COMPRADOR).sum()))


def configurar_colunas_e_processar(df, origem_texto):
    df.columns = [str(c).strip() for c in df.columns]

    st.info(
        f"Regra aplicada: usa a **menor Data Prev Entrega do pedido**. "
        f"Hoje a cobrança considera somente pedidos com menor data até "
        f"**{data_br(data_limite_cobranca())}**."
    )

    st.subheader("Prévia do arquivo")
    st.caption(origem_texto)
    st.dataframe(df.head(30), use_container_width=True)

    linhas_todas, linhas_cobranca, avisos, colunas, agrupado = preparar_linhas(df)

    st.subheader("Colunas identificadas automaticamente")

    colunas_df = pd.DataFrame([
        {"Campo usado": "Pedido", "Coluna encontrada": colunas.get("pedido")},
        {"Campo usado": "Departamento", "Coluna encontrada": colunas.get("departamento")},
        {"Campo usado": "Fornecedor", "Coluna encontrada": colunas.get("fornecedor")},
        {"Campo usado": "Menor Data Prev Entrega", "Coluna encontrada": colunas.get("data_prev_entrega")},
        {"Campo usado": "Saldo CMV", "Coluna encontrada": colunas.get("saldo_cmv")},
        {"Campo usado": "Pré Nota CMV", "Coluna encontrada": colunas.get("pre_nota_cmv")},
        {"Campo usado": "Não Faturado CMV", "Coluna encontrada": colunas.get("nao_faturado_cmv")},
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
    total_geral = sum(x["valor_total_cmv"] for x in linhas_cobranca)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pedidos no arquivo", len(linhas_todas))
    c2.metric("Entram na cobrança", len(linhas_cobranca))
    c3.metric("Fora por data", len(linhas_todas) - len(linhas_cobranca))
    c4.metric("Valor total CMV", formatar_moeda(total_geral))

    c5, c6, c7 = st.columns(3)
    c5.metric("Saldo CMV", formatar_moeda(total_saldo))
    c6.metric("Pré Nota CMV", formatar_moeda(total_pre_nota))
    c7.metric("Não Faturado CMV", formatar_moeda(total_nao_faturado))

    if not preview_cobranca.empty:
        st.subheader("Separação dos atrasados por analista")

        resumo = preview_cobranca.groupby(
            ["analista", "departamento"],
            dropna=False
        ).agg(
            pedidos=("pedido", "count"),
            saldo_cmv=("saldo_cmv", "sum"),
            pre_nota_cmv=("pre_nota_cmv", "sum"),
            nao_faturado_cmv=("nao_faturado_cmv", "sum"),
            valor_total_cmv=("valor_total_cmv", "sum")
        ).reset_index()

        st.dataframe(resumo, use_container_width=True, hide_index=True)

        sem_analista = preview_cobranca[preview_cobranca["analista"] == "SEM ANALISTA"]

        if not sem_analista.empty:
            st.warning("Existem departamentos em atraso sem analista. Confira a escrita do departamento.")
            st.dataframe(
                sem_analista[[
                    "pedido", "departamento", "dt_agendada", "fornecedor",
                    "saldo_cmv", "pre_nota_cmv", "nao_faturado_cmv", "valor_total_cmv"
                ]].head(50),
                use_container_width=True,
                hide_index=True
            )

    with st.expander("Ver pedidos que entrarão na cobrança"):
        if preview_cobranca.empty:
            st.write("Nenhum pedido entra na cobrança pelo critério de data.")
        else:
            st.dataframe(preview_cobranca.head(300), use_container_width=True, hide_index=True)

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

        st.success("Carteira processada com sucesso!")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total no arquivo", resultado["total_arquivo"])
        c2.metric("Entraram na cobrança", resultado["em_atraso"])
        c3.metric("Retirados por data", resultado["retirados_por_data"])
        c4.metric("Retirados da conta", resultado["cancelados"])

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Novos", resultado["novos"])
        c6.metric("Mantidos", resultado["mantidos"])
        c7.metric("Reativados", resultado["reativados"])
        c8.metric("Fora do atraso", resultado["fora_atraso"])


def tela_upload():
    st.header("📤 Atualizar carteira")

    st.warning(
        "A cobrança será montada somente com a menor Data Prev Entrega do pedido até ontem. "
        "Exemplo: hoje cobra até ontem; amanhã cobra até hoje. "
        "Pedido que sumir do arquivo será retirado da conta, não será marcado como entregue."
    )

    arquivo = st.file_uploader("Arquivo da carteira", type=["xlsx", "xls", "csv"])

    if not arquivo:
        st.info("Envie o arquivo da carteira para atualizar a base.")
        return

    df = ler_arquivo(arquivo)
    configurar_colunas_e_processar(df, f"Origem: upload manual - {arquivo.name}")


def tela_carteira(analista=None):
    titulo = "📌 Minha carteira em atraso" if analista else "📌 Carteira geral em atraso"
    st.header(titulo)

    st.info(f"Data limite da cobrança hoje: **{data_br(data_limite_cobranca())}**")

    itens = buscar_docs(ativos=True)
    df = montar_df_itens(itens)

    if analista:
        df = df[df["analista"] == analista] if not df.empty else df

    metricas(df)

    if df.empty:
        st.info("Nenhum pedido ativo em atraso encontrado.")
        return

    df_filtrado = aplicar_filtros(
        df,
        pode_filtrar_analista=(analista is None),
        key_prefix="carteira_geral" if analista is None else f"carteira_{analista}"
    )

    st.subheader("Pedidos em atraso para cobrar")
    st.dataframe(
        df_filtrado.drop(columns=["doc_id"], errors="ignore"),
        use_container_width=True,
        hide_index=True
    )

    csv = df_filtrado.drop(
        columns=["doc_id"],
        errors="ignore"
    ).to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        "Baixar carteira filtrada em CSV",
        data=csv,
        file_name="carteira_cobranca_atraso.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.subheader("Ações de cobrança")

    for _, linha in df_filtrado.iterrows():
        doc_id = linha["doc_id"]
        status = linha.get("status", STATUS_PENDENTE)
        cobrancas = int(linha.get("cobrancas", 0) or 0)

        with st.expander(
            f"Pedido {linha.get('pedido', '-')} | "
            f"Menor data {linha.get('dt_agendada', '-')} | "
            f"{linha.get('departamento', '-')} | "
            f"{linha.get('fornecedor', '-')}"
        ):
            st.markdown(
                f"""
                <div class="card">
                    <b>Status:</b> {badge(status)}<br>
                    <b>Analista:</b> {linha.get('analista', '-')}<br>
                    <b>Departamento:</b> {linha.get('departamento', '-')}<br>
                    <b>Menor Data Prev Entrega:</b> {linha.get('dt_agendada', '-') or '-'}<br>
                    <b>Fornecedor:</b> {linha.get('fornecedor', '-') or '-'}<br>
                    <b>Qtd. itens do pedido:</b> {linha.get('qtd_itens', 0)}<br>
                    <b>Saldo CMV:</b> {formatar_moeda(linha.get('saldo_cmv', 0))}<br>
                    <b>Pré Nota CMV:</b> {formatar_moeda(linha.get('pre_nota_cmv', 0))}<br>
                    <b>Não Faturado CMV:</b> {formatar_moeda(linha.get('nao_faturado_cmv', 0))}<br>
                    <b>Valor Total CMV:</b> {formatar_moeda(linha.get('valor_total_cmv', 0))}<br>
                    <b>Cobranças:</b> {cobrancas}<br>
                    <b>Última cobrança:</b> {linha.get('ultima_cobranca', '') or '-'}
                </div>
                """,
                unsafe_allow_html=True
            )

            obs = st.text_area(
                "Observação da cobrança",
                key=f"obs_{doc_id}",
                placeholder="Ex.: cobrado fornecedor por e-mail/WhatsApp, retorno previsto..."
            )

            col_a, col_b = st.columns(2)

            if cobrancas == 2 and status != STATUS_COMPRADOR_ACIONADO:
                st.warning("A próxima cobrança será a 3ª. Pela regra, o comprador deve ser acionado.")

            with col_a:
                if st.button(
                    "Registrar cobrança",
                    key=f"cobrar_{doc_id}",
                    use_container_width=True
                ):
                    registrar_cobranca(doc_id, usuario_logado, obs)
                    st.success("Cobrança registrada.")
                    st.rerun()

            with col_b:
                desabilitar = (
                    status not in [STATUS_ACIONAR_COMPRADOR, STATUS_COMPRADOR_ACIONADO]
                    and cobrancas < 3
                )

                if st.button(
                    "Marcar comprador acionado",
                    key=f"comprador_{doc_id}",
                    use_container_width=True,
                    disabled=desabilitar
                ):
                    marcar_comprador_acionado(doc_id, usuario_logado, obs)
                    st.success("Comprador acionado registrado.")
                    st.rerun()

            item_completo = buscar_doc(doc_id)
            historico = item_completo.get("historico", []) if item_completo else []

            if historico:
                hist_df = pd.DataFrame(historico).sort_values("data", ascending=False)
                st.caption("Histórico")
                st.dataframe(hist_df, use_container_width=True, hide_index=True)


def tela_fora_atraso():
    st.header("📅 Fora do atraso")

    itens = buscar_docs(ativos=False)
    df = montar_df_itens(itens)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum pedido fora do atraso.")
        return

    df = df[df["status"] == STATUS_FORA_ATRASO]

    if df.empty:
        st.info("Nenhum pedido fora do atraso.")
        return

    df_filtrado = aplicar_filtros(df, pode_filtrar_analista=True, key_prefix="fora_atraso")

    st.metric("Fora do atraso", len(df_filtrado))

    st.dataframe(
        df_filtrado.drop(columns=["doc_id"], errors="ignore"),
        use_container_width=True,
        hide_index=True
    )


def tela_cancelados():
    st.header("🚫 Retirados da conta")

    itens = buscar_docs(ativos=False)
    df = montar_df_itens(itens)

    if df.empty or "status" not in df.columns:
        st.info("Nenhum pedido retirado da conta.")
        return

    df = df[df["status"] == STATUS_CANCELADO]

    if df.empty:
        st.info("Nenhum pedido retirado da conta.")
        return

    df_filtrado = aplicar_filtros(df, pode_filtrar_analista=True, key_prefix="cancelados")

    st.metric("Retirados da conta", len(df_filtrado))

    st.dataframe(
        df_filtrado.drop(columns=["doc_id"], errors="ignore"),
        use_container_width=True,
        hide_index=True
    )


def tela_regras():
    st.header("⚙️ Regras e departamentos")

    st.subheader("Regra da data")
    st.write(f"Hoje é {data_br(hoje())}.")
    st.write(f"A carteira de cobrança considera somente pedidos com menor Data Prev Entrega até {data_br(data_limite_cobranca())}.")
    st.write("Se o pedido tiver vários itens, o sistema usa a menor Data Prev Entrega.")
    st.write("Pedidos com menor Data Prev Entrega de hoje ou futura ficam fora da cobrança.")
    st.write("Se o pedido sumir do arquivo completo, ele será retirado da cobrança e da contagem.")
    st.write("Não existe regra de marcar como entregue.")

    st.subheader("Valores considerados")
    st.write("Valor Total CMV = Saldo R$ (CMV) + Pré Nota R$ (CMV) + Não Faturado R$ (CMV).")

    st.subheader("Analistas")

    for analista, deps in ANALISTAS.items():
        st.markdown(f"**{analista}**: {', '.join(deps)}")

    st.subheader("Regra da cobrança")
    st.write("1. Pedido atrasado entrou na carteira: fica como pendente.")
    st.write("2. Clicou em registrar cobrança 1 vez: status Cobrado 1x.")
    st.write("3. Clicou em registrar cobrança 2 vezes: status Cobrado 2x.")
    st.write("4. Na 3ª cobrança: status muda para Acionar Comprador.")
    st.write("5. Quando o comprador for acionado, marque no sistema.")
    st.write("6. Se o pedido sair do arquivo, ele sai da conta como Cancelado / Retirado.")

# =========================
# ROTEAMENTO
# =========================
st.title("📋 Cobrança de Carteira")
st.caption("Controle de pedidos atrasados por analista, departamento, comprador e status de cobrança.")

if usuario_logado == "Admin":
    aba_upload, aba_geral, aba_fora, aba_cancelados, aba_regras = st.tabs([
        "Atualizar", "Carteira Geral", "Fora do Atraso", "Retirados da Conta", "Regras"
    ])

    with aba_upload:
        tela_upload()

    with aba_geral:
        tela_carteira()

    with aba_fora:
        tela_fora_atraso()

    with aba_cancelados:
        tela_cancelados()

    with aba_regras:
        tela_regras()

else:
    aba_minha, aba_regras = st.tabs([
        "Minha Carteira", "Regras"
    ])

    with aba_minha:
        tela_carteira(usuario_logado)

    with aba_regras:
        tela_regras()
