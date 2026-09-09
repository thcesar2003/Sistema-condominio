import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re
import unicodedata
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

# ============================================================
# SAN REMO - GESTÃO FINANCEIRA CONDOMINIAL
# Versão: 2026.09 - relatório, fundo e saldo corrigidos
# ============================================================

st.set_page_config(
    page_title="San Remo • Gestão Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

URL_DRIVE = "https://drive.google.com/uc?export=download&id=1DY8-BcxRhWZYPW2rhf07sZBraZk5akTe"
NOME_FUNDO = "Fundo de reserva"
NOME_ANTENAS = "Locações de espaço - Antenas"

# ============================================================
# FUNÇÕES BÁSICAS
# ============================================================

def normalizar_texto(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().lower()
    return unicodedata.normalize("NFKD", texto).encode(
        "ascii", "ignore"
    ).decode("ascii")


def dinheiro(valor):
    try:
        return (
            f"R$ {float(valor):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    except Exception:
        return "R$ 0,00"


def limpar_valor(serie):
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    s = serie.astype(str).str.strip()
    s = s.str.replace("R$", "", regex=False)
    s = s.str.replace(" ", "", regex=False)
    s = s.str.replace("(", "-", regex=False)
    s = s.str.replace(")", "", regex=False)

    # Trata valores brasileiros: 1.234,56
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


def encontrar_coluna(df, nomes, evitar=None):
    evitar = evitar or []
    mapa = {normalizar_texto(c): c for c in df.columns}

    # Primeiro tenta correspondência exata.
    for nome in nomes:
        chave = normalizar_texto(nome)
        if chave in mapa and mapa[chave] not in evitar:
            return mapa[chave]

    # Depois procura por trecho.
    for c in df.columns:
        if c in evitar:
            continue
        nc = normalizar_texto(c)
        if any(normalizar_texto(n) in nc for n in nomes):
            return c

    return None


def nome_mes(periodo):
    nomes = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    try:
        p = pd.Period(periodo, freq="M")
        return f"{nomes[p.month]} de {p.year}"
    except Exception:
        return str(periodo)


def safe_str(valor):
    if pd.isna(valor):
        return ""
    return str(valor)


# ============================================================
# CLASSIFICAÇÃO
# ============================================================

REGRAS = {
    "Consumo - Água": [
        "sabesp", "saae", "agua", "saneamento", "esgoto"
    ],
    "Consumo - Energia": [
        "enel", "edp", "elektro", "energia eletrica", "energia"
    ],
    "Consumo - Gás": [
        "comgas", "gas natural", "gas encanado", "gas"
    ],
    "Consumo - Telefone/Internet": [
        "vivo", "claro", "tim", "oi ", "telefonia",
        "internet", "fibra", "telefon"
    ],

    "Salários": [
        "salario", "folha", "pagamento funcionario",
        "pagamento de funcionario", "pro labore", "pro-labore"
    ],
    "Funcionários - Encargos": [
        "fgts", "inss", "gps", "e-social", "esocial",
        "irrf", "contribuicao previdenciaria"
    ],
    "Funcionários - Benefícios": [
        "vale transporte", "vt ", "vale refeicao",
        "vale alimentacao", "alelo", "ticket",
        "cesta basica", "beneficio"
    ],
    "Funcionários - Férias/13º": [
        "ferias", "decimo terceiro", "13 salario",
        "13º", "abono"
    ],
    "Funcionários - Rescisões": [
        "rescisao", "multa fgts", "aviso previo"
    ],

    "Terceirização - Portaria/Segurança": [
        "portaria", "seguranca", "vigilancia",
        "vigia", "controlador de acesso"
    ],
    "Terceirização - Limpeza": [
        "limpeza terceirizada", "conservacao", "asseio"
    ],

    "Administradora": [
        "administradora", "assessoria condominial",
        "gestao condominial"
    ],
    "Garantidora": [
        "garantidora", "garantia de recebiveis"
    ],

    "Elevadores": [
        "elevador", "elevadores", "qualita",
        "manutencao elevador"
    ],
    "Manutenção": [
        "manutencao", "conserto", "reparo",
        "assistencia tecnica"
    ],
    "Limpeza/Material": [
        "material de limpeza", "produto de limpeza",
        "detergente", "desinfetante", "saco de lixo"
    ],
    "Jardinagem": [
        "jardinagem", "jardim", "paisagismo", "poda"
    ],
    "Piscina": [
        "piscina", "cloro", "tratamento piscina"
    ],
    "Segurança Eletrônica": [
        "intelbras", "cftv", "camera", "alarme",
        "monitoramento"
    ],
    "Equipamentos": [
        "bomba", "motor", "gerador", "equipamento"
    ],
    "Obras/Reformas": [
        "obra", "reforma", "pintura",
        "impermeabilizacao", "construcao"
    ],
    "Seguros": [
        "seguro", "apolice"
    ],
    "Impostos/Taxas": [
        "tributo", "imposto", "taxa", "iss",
        "darf", "prefeitura"
    ],
    "Bancárias": [
        "tarifa bancaria", "tarifa", "banco",
        "ted", "pix tarifa"
    ],
    "Jurídico": [
        "advogado", "advocacia", "juridico", "processo"
    ],
    "Contabilidade": [
        "contabilidade", "contador", "contabil"
    ],
}


def classificar_linha(row, col_valor, col_lanc, col_cnpj, col_razao):
    txt_lanc = normalizar_texto(
        row.get(col_lanc, "")
    ) if col_lanc else ""

    txt_cnpj = (
        str(row.get(col_cnpj, "")).strip()
        if col_cnpj and pd.notna(row.get(col_cnpj))
        else ""
    )

    txt_razao = normalizar_texto(
        row.get(col_razao, "")
    ) if col_razao else ""

    valor = row.get(col_valor, 0)
    tipo = (
        "Entrada" if valor > 0
        else "Saída" if valor < 0
        else "Neutro"
    )

    texto = f"{txt_lanc} {txt_razao} {txt_cnpj}".strip()
    texto_limpo = normalizar_texto(texto)
    cnpj_limpo = re.sub(r"\D", "", txt_cnpj)

    # --------------------------------------------------------
    # 1. FUNDO DE RESERVA - PRIORIDADE MÁXIMA
    # --------------------------------------------------------
    # Transferência da conta corrente para a aplicação:
    # NÃO é despesa operacional.
    # É uma transferência patrimonial que reduz o saldo da
    # conta corrente e aumenta positivamente o fundo acumulado.
    termos_fundo = [
        "aplicacao privilege int",
        "privilege int",
        "aplicacao privilege",
        "privilege"
    ]
    if any(t in texto_limpo for t in termos_fundo):
        return NOME_FUNDO

    # --------------------------------------------------------
    # 2. LOCAÇÕES DE ESPAÇO - ANTENAS
    # --------------------------------------------------------
    # Universal Telecom e Directnet são ARRECADAÇÃO/RECEITA
    # proveniente de locação de espaço, e NÃO manutenção.
    termos_antenas = [
        "universal telecom",
        "universal telecom ltda",
        "directnet",
        "direct net"
    ]

    if any(t in texto_limpo for t in termos_antenas):
        return NOME_ANTENAS

    # --------------------------------------------------------
    # 3. OUTRAS RECEITAS ESPECÍFICAS
    # --------------------------------------------------------
    if (
        "51877768000189" in cnpj_limpo
        or "51877768000189" in re.sub(r"\D", "", texto_limpo)
    ):
        return "Mercadinho"

    # Entrada de R$ 150,00 = salão de festas
    if tipo == "Entrada" and abs(float(valor) - 150.0) < 0.01:
        return "Salão de festas"

    # --------------------------------------------------------
    # 4. CLASSIFICAÇÃO GERAL
    # --------------------------------------------------------
    for categoria, palavras in REGRAS.items():
        for palavra in palavras:
            if normalizar_texto(palavra) in texto_limpo:
                return categoria

    return (
        "Outras Despesas"
        if tipo == "Saída"
        else "Receitas"
    )


# ============================================================
# CARREGAMENTO DO GOOGLE DRIVE
# ============================================================

@st.cache_data(ttl=300)
def carregar_dados():
    raw = pd.read_excel(URL_DRIVE, header=None)

    linha_cabecalho = 0

    for idx, row in raw.iterrows():
        linha = " ".join(
            normalizar_texto(v)
            for v in row.values
            if pd.notna(v)
        )

        if (
            "valor" in linha
            or "data" in linha
            or "lancamento" in linha
            or "historico" in linha
        ):
            linha_cabecalho = idx
            break

    return pd.read_excel(
        URL_DRIVE,
        header=linha_cabecalho
    )


try:
    df = carregar_dados()
except Exception as e:
    st.error(
        "Não foi possível ler o arquivo do Google Drive."
    )
    st.exception(e)
    st.stop()


df.columns = [str(c).strip() for c in df.columns]

# ============================================================
# IDENTIFICAÇÃO DAS COLUNAS
# ============================================================

col_valor = encontrar_coluna(
    df,
    ["valor", "valor r$", "valor (r$)", "amount"]
)

col_data = encontrar_coluna(
    df,
    ["data", "data lançamento", "data lancamento", "date"]
)

col_lanc = encontrar_coluna(
    df,
    ["lançamento", "lancamento", "histórico", "historico"]
)

col_cnpj = encontrar_coluna(
    df,
    ["cpf/cnpj", "cpf", "cnpj", "documento"]
)

col_razao = encontrar_coluna(
    df,
    ["razão social", "razao social", "fornecedor", "favorecido"]
)

# Saldo: procura primeiro nomes exatos, evitando colunas de
# saldo de investimento/aplicação quando houver.
col_saldo = encontrar_coluna(
    df,
    [
        "saldo conta corrente",
        "saldo corrente",
        "saldo disponível",
        "saldo disponivel",
        "saldo atual",
        "saldo",
        "balance"
    ]
)

if not col_valor:
    st.error("Não encontrei a coluna de valor no extrato.")
    st.write("Colunas encontradas:", list(df.columns))
    st.stop()

# ============================================================
# PREPARAÇÃO
# ============================================================

df[col_valor] = limpar_valor(df[col_valor])
df = df.dropna(subset=[col_valor]).copy()

if col_data:
    df["Data_Analise"] = pd.to_datetime(
        df[col_data],
        dayfirst=True,
        errors="coerce"
    )
else:
    df["Data_Analise"] = pd.NaT

df["Tipo_Calculado"] = df[col_valor].apply(
    lambda x:
        "Entrada" if x > 0
        else "Saída" if x < 0
        else "Neutro"
)

df["Valor_Absoluto"] = df[col_valor].abs()

df["Categoria"] = df.apply(
    lambda row: classificar_linha(
        row,
        col_valor,
        col_lanc,
        col_cnpj,
        col_razao
    ),
    axis=1
)

# ============================================================
# SALDO DO EXTRATO
# ============================================================

if col_saldo:
    df["Saldo_Extrato"] = limpar_valor(df[col_saldo])
else:
    df["Saldo_Extrato"] = pd.Series(
        pd.NA,
        index=df.index,
        dtype="Float64"
    )

df["Mes"] = (
    df["Data_Analise"]
    .dt.to_period("M")
    .astype(str)
)

df.loc[
    df["Data_Analise"].isna(),
    "Mes"
] = "Sem data"

# ============================================================
# IDENTIFICAÇÃO DO FUNDO
# ============================================================

df["Eh_Fundo"] = df["Categoria"].eq(NOME_FUNDO)
df["Eh_Receita"] = (
    (df["Tipo_Calculado"] == "Entrada")
    & (~df["Eh_Fundo"])
)

df["Eh_Despesa"] = (
    (df["Tipo_Calculado"] == "Saída")
    & (~df["Eh_Fundo"])
)

df["Eh_Transferencia_Fundo"] = df["Eh_Fundo"]

# ============================================================
# FUNÇÕES FINANCEIRAS
# ============================================================

def resumo_periodo(d):
    entradas = d.loc[
        d["Eh_Receita"],
        "Valor_Absoluto"
    ].sum()

    despesas = d.loc[
        d["Eh_Despesa"],
        "Valor_Absoluto"
    ].sum()

    fundo_transferido = d.loc[
        d["Eh_Transferencia_Fundo"],
        "Valor_Absoluto"
    ].sum()

    resultado_operacional = entradas - despesas

    # Movimento efetivo da conta corrente.
    # Entradas entram; despesas saem; fundo é transferido
    # da conta corrente para investimento e, portanto, também
    # reduz o saldo da conta corrente.
    movimento_conta = entradas - despesas - fundo_transferido

    return {
        "entradas": float(entradas),
        "despesas": float(despesas),
        "fundo": float(fundo_transferido),
        "resultado": float(resultado_operacional),
        "movimento_conta": float(movimento_conta),
    }


def construir_saldos_mensais(df_base, saldo_inicial):
    """
    Calcula o saldo final de cada mês.

    Regra:
        saldo final = saldo inicial + entradas
                      - despesas
                      - transferência para fundo

    Se o extrato tiver uma coluna de saldo confiável,
    ela é usada como referência/validação.

    Se não tiver, o cálculo é automático e o saldo de um mês
    passa integralmente para o mês seguinte.
    """
    d = df_base[
        df_base["Data_Analise"].notna()
    ].copy()

    if d.empty:
        return pd.DataFrame()

    d["Ano_Mes"] = (
        d["Data_Analise"]
        .dt.to_period("M")
        .astype(str)
    )

    meses = sorted(d["Ano_Mes"].unique())

    saldo_atual = float(saldo_inicial)
    linhas = []

    for mes in meses:
        grupo = d[d["Ano_Mes"] == mes].copy()
        grupo = grupo.sort_values(
            ["Data_Analise"]
        )

        r = resumo_periodo(grupo)

        saldo_calculado = (
            saldo_atual
            + r["entradas"]
            - r["despesas"]
            - r["fundo"]
        )

        saldo_extrato = None

        if "Saldo_Extrato" in grupo.columns:
            validos = grupo[
                grupo["Saldo_Extrato"].notna()
            ]

            if not validos.empty:
                # Último saldo disponível do mês.
                saldo_extrato = float(
                    validos.iloc[-1]["Saldo_Extrato"]
                )

        linhas.append({
            "Mês": mes,
            "Data final": grupo["Data_Analise"].max(),
            "Entradas": r["entradas"],
            "Despesas": r["despesas"],
            "Fundo transferido": r["fundo"],
            "Resultado operacional": r["resultado"],
            "Movimento conta corrente": r["movimento_conta"],
            "Saldo calculado": saldo_calculado,
            "Saldo do extrato": saldo_extrato,
        })

        saldo_atual = saldo_calculado

    out = pd.DataFrame(linhas)

    # Se existe saldo no extrato, usa o saldo real como base para
    # o próximo mês, pois ele é a melhor fonte do saldo bancário.
    # Se não existe, mantém o saldo calculado.
    if not out.empty:
        saldo_corrente = float(saldo_inicial)

        for i in out.index:
            saldo_ext = out.at[i, "Saldo do extrato"]

            if pd.notna(saldo_ext):
                saldo_corrente = float(saldo_ext)
                out.at[i, "Saldo final"] = saldo_corrente
            else:
                saldo_corrente = float(
                    out.at[i, "Saldo calculado"]
                )
                out.at[i, "Saldo final"] = saldo_corrente

            # O saldo final desta linha é exatamente o saldo
            # que será levado para o mês seguinte.

    return out


def fundo_mensal_acumulado(df_base):
    d = df_base[
        (df_base["Eh_Fundo"])
        & df_base["Data_Analise"].notna()
    ].copy()

    if d.empty:
        return pd.DataFrame(
            columns=["Mês", "Fundo no mês", "Fundo acumulado"]
        )

    d["Mês"] = (
        d["Data_Analise"]
        .dt.to_period("M")
        .astype(str)
    )

    out = (
        d.groupby("Mês")["Valor_Absoluto"]
        .sum()
        .reset_index()
        .sort_values("Mês")
    )

    out = out.rename(
        columns={"Valor_Absoluto": "Fundo no mês"}
    )

    out["Fundo acumulado"] = (
        out["Fundo no mês"].cumsum()
    )

    return out


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("🔍 Filtros avançados")

if st.sidebar.button("🔄 Atualizar dados do Drive"):
    st.cache_data.clear()
    st.rerun()

# Saldo inicial configurável.
# É usado somente quando não existe saldo no extrato ou para
# validar/calcular o encadeamento mensal.
saldo_inicial = st.sidebar.number_input(
    "🏦 Saldo inicial da conta",
    min_value=-100000000.0,
    max_value=100000000.0,
    value=0.0,
    step=100.0,
    format="%.2f",
    help=(
        "Informe o saldo existente antes do primeiro mês "
        "do extrato. O saldo final de cada mês será levado "
        "automaticamente para o mês seguinte."
    )
)

tipo = st.sidebar.selectbox(
    "Tipo de lançamento",
    ["Todos", "Entrada", "Saída"]
)

categorias = sorted(
    df["Categoria"]
    .dropna()
    .unique()
    .tolist()
)

categorias_sel = st.sidebar.multiselect(
    "Categoria",
    categorias
)

meses = sorted(
    df["Mes"]
    .dropna()
    .unique()
    .tolist()
)

meses_sel = st.sidebar.multiselect(
    "Mês",
    meses
)

busca = st.sidebar.text_input(
    "🔎 Pesquisa",
    placeholder="Fornecedor, CNPJ, lançamento..."
)

valor_max = (
    float(df["Valor_Absoluto"].max())
    if len(df)
    else 1.0
)

faixa = st.sidebar.slider(
    "Faixa de valor (R$)",
    min_value=0.0,
    max_value=max(valor_max, 1.0),
    value=(0.0, max(valor_max, 1.0))
)

somente_func = st.sidebar.checkbox(
    "👷 Somente funcionários"
)

somente_consumo = st.sidebar.checkbox(
    "💡 Somente consumo"
)

somente_manut = st.sidebar.checkbox(
    "🛠️ Somente manutenção"
)

somente_receitas = st.sidebar.checkbox(
    "💰 Somente arrecadação/receitas"
)

somente_fundo = st.sidebar.checkbox(
    "🏦 Somente fundo de reserva"
)

# ============================================================
# APLICAÇÃO DOS FILTROS
# ============================================================

df_filtrado = df.copy()

if tipo != "Todos":
    df_filtrado = df_filtrado[
        df_filtrado["Tipo_Calculado"] == tipo
    ]

if categorias_sel:
    df_filtrado = df_filtrado[
        df_filtrado["Categoria"].isin(categorias_sel)
    ]

if meses_sel:
    df_filtrado = df_filtrado[
        df_filtrado["Mes"].isin(meses_sel)
    ]

if busca:
    mascara = pd.Series(
        False,
        index=df_filtrado.index
    )

    campos = [
        c for c in [
            col_lanc,
            col_razao,
            col_cnpj,
            "Categoria"
        ]
        if c
    ]

    for c in dict.fromkeys(campos):
        if c in df_filtrado.columns:
            mascara |= (
                df_filtrado[c]
                .astype(str)
                .str.contains(
                    busca,
                    case=False,
                    na=False,
                    regex=False
                )
            )

    df_filtrado = df_filtrado[mascara]

df_filtrado = df_filtrado[
    (df_filtrado["Valor_Absoluto"] >= faixa[0])
    & (df_filtrado["Valor_Absoluto"] <= faixa[1])
]

if somente_func:
    df_filtrado = df_filtrado[
        df_filtrado["Categoria"].str.contains(
            "Salários|Funcionários",
            case=False,
            na=False
        )
    ]

if somente_consumo:
    df_filtrado = df_filtrado[
        df_filtrado["Categoria"].str.startswith(
            "Consumo",
            na=False
        )
    ]

if somente_manut:
    categorias_manut = [
        "Manutenção",
        "Elevadores",
        "Segurança Eletrônica",
        "Equipamentos",
        "Obras/Reformas",
        "Jardinagem",
        "Piscina",
    ]
    df_filtrado = df_filtrado[
        df_filtrado["Categoria"].isin(
            categorias_manut
        )
    ]

if somente_receitas:
    df_filtrado = df_filtrado[
        df_filtrado["Eh_Receita"]
    ]

if somente_fundo:
    df_filtrado = df_filtrado[
        df_filtrado["Eh_Fundo"]
    ]

# ============================================================
# SALDOS GERAIS - SEM FILTRO DE CATEGORIA
# ============================================================

saldos_gerais = construir_saldos_mensais(
    df,
    saldo_inicial
)

saldo_final_geral = None

if not saldos_gerais.empty:
    saldo_final_geral = float(
        saldos_gerais.iloc[-1]["Saldo final"]
    )

fundo_geral = fundo_mensal_acumulado(df)

fundo_total = (
    float(fundo_geral["Fundo acumulado"].iloc[-1])
    if not fundo_geral.empty
    else 0.0
)

# ============================================================
# CABEÇALHO
# ============================================================

logo_col, titulo_col = st.columns([1, 6])

with logo_col:
    try:
        st.image("logo.jpg", width=110)
    except Exception:
        st.write("🏢")

with titulo_col:
    st.title("Condomínio Jardim San Remo")
    st.caption(
        "Gestão financeira • Arrecadação • Despesas • "
        "Consumo • Funcionários • Manutenção • "
        "Fundo de Reserva • Saldo bancário"
    )

# ============================================================
# KPIs
# ============================================================

resumo = resumo_periodo(df_filtrado)

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric(
    "💰 Arrecadação",
    dinheiro(resumo["entradas"])
)

c2.metric(
    "💸 Despesas",
    dinheiro(resumo["despesas"])
)

c3.metric(
    "📈 Resultado operacional",
    dinheiro(resumo["resultado"])
)

c4.metric(
    "🏦 Fundo acumulado",
    dinheiro(fundo_total)
)

c5.metric(
    "🏦 Saldo final",
    dinheiro(saldo_final_geral)
    if saldo_final_geral is not None
    else "R$ 0,00"
)

c6.metric(
    "📋 Lançamentos",
    f"{len(df_filtrado):,}".replace(",", ".")
)

# ============================================================
# ABAS
# ============================================================

tabs = st.tabs([
    "📊 Dashboard",
    "📅 Relatório Mensal",
    "📄 PDF Mensal",
    "🏦 Fundo de Reserva",
    "🏦 Saldo Bancário",
    "💰 Arrecadação",
    "👷 Funcionários",
    "💡 Consumo",
    "🛠️ Manutenção",
    "💸 Despesas",
    "🔎 Pesquisa",
    "🧠 Classificação",
    "📋 Dados",
])

# ============================================================
# DASHBOARD
# ============================================================

with tabs[0]:
    st.subheader("📊 Dashboard financeiro")

    if df_filtrado.empty:
        st.warning(
            "Nenhum lançamento corresponde aos filtros."
        )
    else:
        d = df_filtrado[
            df_filtrado["Data_Analise"].notna()
        ].copy()

        if not d.empty:
            d["Ano_Mes"] = (
                d["Data_Analise"]
                .dt.to_period("M")
                .astype(str)
            )

            mensal = []

            for mes, grupo in d.groupby(
                "Ano_Mes",
                sort=True
            ):
                r = resumo_periodo(grupo)

                mensal.append({
                    "Mês": mes,
                    "Entradas": r["entradas"],
                    "Despesas": r["despesas"],
                    "Resultado": r["resultado"],
                    "Fundo": r["fundo"],
                })

            mensal_df = pd.DataFrame(mensal)

            comp = mensal_df.melt(
                id_vars=["Mês"],
                value_vars=[
                    "Entradas",
                    "Despesas"
                ],
                var_name="Tipo",
                value_name="Valor"
            )

            fig = px.bar(
                comp,
                x="Mês",
                y="Valor",
                color="Tipo",
                barmode="group",
                title=(
                    "Entradas x Despesas — "
                    "resultado operacional"
                ),
                labels={
                    "Mês": "Mês",
                    "Valor": "Valor (R$)",
                    "Tipo": ""
                }
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            st.subheader("📈 Resultado mensal")

            fig_resultado = px.bar(
                mensal_df,
                x="Mês",
                y="Resultado",
                title="Resultado operacional por mês",
                labels={
                    "Resultado": "Resultado (R$)",
                    "Mês": "Mês"
                }
            )

            st.plotly_chart(
                fig_resultado,
                use_container_width=True
            )

            st.subheader(
                "🏦 Fundo de Reserva acumulado"
            )

            fundo_dash = fundo_mensal_acumulado(
                df_filtrado
            )

            if not fundo_dash.empty:
                fig_fundo = px.line(
                    fundo_dash,
                    x="Mês",
                    y="Fundo acumulado",
                    markers=True,
                    title=(
                        "Fundo de Reserva acumulado"
                    ),
                    labels={
                        "Fundo acumulado": "R$",
                        "Mês": "Mês"
                    }
                )

                st.plotly_chart(
                    fig_fundo,
                    use_container_width=True
                )

        a, b = st.columns(2)

        with a:
            operacional = df_filtrado[
                ~df_filtrado["Eh_Fundo"]
            ]

            tipo_df = (
                operacional
                .groupby("Tipo_Calculado")[
                    "Valor_Absoluto"
                ]
                .sum()
                .reset_index()
            )

            fig = px.pie(
                tipo_df,
                names="Tipo_Calculado",
                values="Valor_Absoluto",
                hole=.45,
                title="Proporção operacional"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        with b:
            despesas = df_filtrado[
                df_filtrado["Eh_Despesa"]
            ]

            cat = (
                despesas
                .groupby("Categoria")[
                    "Valor_Absoluto"
                ]
                .sum()
                .nlargest(10)
                .sort_values()
            )

            fig = px.bar(
                cat.reset_index(),
                x="Valor_Absoluto",
                y="Categoria",
                orientation="h",
                title="Top 10 despesas"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

# ============================================================
# RELATÓRIO MENSAL
# ============================================================

with tabs[1]:
    st.subheader("📅 Relatório financeiro mensal")

    if saldos_gerais.empty:
        st.warning(
            "Não há datas válidas para montar o relatório."
        )
    else:
        mensal = saldos_gerais.copy()

        mensal["Fundo acumulado"] = (
            mensal["Fundo transferido"].cumsum()
        )

        mensal["Mês"] = mensal["Mês"].apply(
            nome_mes
        )

        tabela = mensal[[
            "Mês",
            "Entradas",
            "Despesas",
            "Resultado operacional",
            "Fundo transferido",
            "Fundo acumulado",
            "Saldo final"
        ]].copy()

        st.dataframe(
            tabela.style.format({
                "Entradas": dinheiro,
                "Despesas": dinheiro,
                "Resultado operacional": dinheiro,
                "Fundo transferido": dinheiro,
                "Fundo acumulado": dinheiro,
                "Saldo final": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        st.info(
            "Regra aplicada: o Fundo de Reserva não entra como "
            "despesa operacional. Porém, como o dinheiro sai da "
            "conta corrente e vai para a aplicação, ele é "
            "subtraído do saldo bancário. O saldo final de um mês "
            "é carregado automaticamente para o mês seguinte."
        )

        # Conferência contábil simples
        st.subheader("🧮 Conferência do mês")

        mes_conf = st.selectbox(
            "Selecione um mês para conferir",
            saldos_gerais["Mês"].tolist(),
            format_func=nome_mes,
            key="mes_conferencia"
        )

        linha = saldos_gerais[
            saldos_gerais["Mês"] == mes_conf
        ].iloc[0]

        cc1, cc2, cc3, cc4 = st.columns(4)

        cc1.metric(
            "Arrecadação",
            dinheiro(linha["Entradas"])
        )
        cc2.metric(
            "Despesas",
            dinheiro(linha["Despesas"])
        )
        cc3.metric(
            "Transferido para fundo",
            dinheiro(linha["Fundo transferido"])
        )
        cc4.metric(
            "Saldo final",
            dinheiro(linha["Saldo final"])
        )

        st.markdown(
            f"""
**Fórmula do saldo do mês**

`Saldo anterior + Arrecadação - Despesas - Fundo de Reserva = Saldo final`

Para **{nome_mes(mes_conf)}**:

`{dinheiro(linha["Saldo calculado"])}`
"""
        )

# ============================================================
# FUNÇÕES DO PDF
# ============================================================

def tabela_pdf(rows, headers, widths):
    tabela = Table(
        [headers] + rows,
        colWidths=widths,
        repeatRows=1
    )

    tabela.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#1E3A8A")
        ),
        (
            "TEXTCOLOR",
            (0, 0),
            (-1, 0),
            colors.white
        ),
        (
            "FONTNAME",
            (0, 0),
            (-1, 0),
            "Helvetica-Bold"
        ),
        (
            "FONTSIZE",
            (0, 0),
            (-1, -1),
            8
        ),
        (
            "GRID",
            (0, 0),
            (-1, -1),
            .35,
            colors.HexColor("#CBD5E1")
        ),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [
                colors.white,
                colors.HexColor("#F8FAFC")
            ]
        ),
        (
            "VALIGN",
            (0, 0),
            (-1, -1),
            "MIDDLE"
        ),
        (
            "ALIGN",
            (-1, 1),
            (-1, -1),
            "RIGHT"
        ),
        (
            "TOPPADDING",
            (0, 0),
            (-1, -1),
            5
        ),
        (
            "BOTTOMPADDING",
            (0, 0),
            (-1, -1),
            5
        ),
    ]))

    return tabela


def gerar_pdf_mensal(
    df_mes,
    mes_nome_txt,
    fundo_acumulado,
    saldo_final
):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=18,
        leading=21,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E3A8A")
    )

    subtitulo = ParagraphStyle(
        "Subtitulo",
        parent=styles["Normal"],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4B5563")
    )

    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#1E3A8A")
    )

    r = resumo_periodo(df_mes)

    story = [
        Paragraph(
            "SAN REMO — RELATÓRIO FINANCEIRO MENSAL",
            titulo
        ),
        Paragraph(
            f"<b>Mês:</b> {mes_nome_txt} &nbsp;&nbsp; "
            f"<b>Emissão:</b> "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')}",
            subtitulo
        ),
        Spacer(1, 12)
    ]

    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    resumo_pdf = [
        [
            "ARRECADAÇÃO",
            "DESPESAS",
            "RESULTADO",
            "FUNDO NO MÊS",
            "FUNDO ACUMULADO",
            "SALDO CONTA"
        ],
        [
            dinheiro(r["entradas"]),
            dinheiro(r["despesas"]),
            dinheiro(r["resultado"]),
            dinheiro(r["fundo"]),
            dinheiro(fundo_acumulado),
            dinheiro(saldo_final)
        ]
    ]

    tabela_resumo = Table(
        resumo_pdf,
        colWidths=[120] * 6
    )

    tabela_resumo.setStyle(TableStyle([
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#F3F4F6")
        ),
        (
            "FONTNAME",
            (0, 0),
            (-1, 0),
            "Helvetica-Bold"
        ),
        (
            "ALIGN",
            (0, 0),
            (-1, -1),
            "CENTER"
        ),
        (
            "GRID",
            (0, 0),
            (-1, -1),
            .5,
            colors.HexColor("#CBD5E1")
        ),
        (
            "FONTSIZE",
            (0, 0),
            (-1, -1),
            8
        ),
        (
            "TOPPADDING",
            (0, 0),
            (-1, -1),
            7
        ),
        (
            "BOTTOMPADDING",
            (0, 0),
            (-1, -1),
            7
        ),
    ]))

    story += [
        tabela_resumo,
        Spacer(1, 15)
    ]

    # --------------------------------------------------------
    # ENTRADAS / ARRECADAÇÃO
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "1. ARRECADAÇÃO / ENTRADAS",
            h2
        )
    )

    entradas = df_mes[
        df_mes["Eh_Receita"]
    ].copy()

    if entradas.empty:
        story.append(
            Paragraph(
                "Nenhuma entrada no período.",
                styles["Normal"]
            )
        )
    else:
        agrupado = (
            entradas
            .groupby("Categoria")[
                "Valor_Absoluto"
            ]
            .sum()
            .sort_values(ascending=False)
        )

        rows = [
            [str(cat), dinheiro(valor)]
            for cat, valor in agrupado.items()
        ]

        rows.append([
            "TOTAL DE ARRECADAÇÃO",
            dinheiro(
                entradas["Valor_Absoluto"].sum()
            )
        ])

        story.append(
            tabela_pdf(
                rows,
                ["Categoria", "Valor"],
                [600, 150]
            )
        )

    story.append(Spacer(1, 12))

    # --------------------------------------------------------
    # DESPESAS
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "2. DESPESAS OPERACIONAIS",
            h2
        )
    )

    despesas = df_mes[
        df_mes["Eh_Despesa"]
    ].copy()

    if despesas.empty:
        story.append(
            Paragraph(
                "Nenhuma despesa no período.",
                styles["Normal"]
            )
        )
    else:
        agrupado = (
            despesas
            .groupby("Categoria")[
                "Valor_Absoluto"
            ]
            .sum()
            .sort_values(ascending=False)
        )

        rows = [
            [str(cat), dinheiro(valor)]
            for cat, valor in agrupado.items()
        ]

        rows.append([
            "TOTAL DE DESPESAS",
            dinheiro(
                despesas["Valor_Absoluto"].sum()
            )
        ])

        story.append(
            tabela_pdf(
                rows,
                ["Categoria", "Valor"],
                [600, 150]
            )
        )

    story.append(Spacer(1, 12))

    # --------------------------------------------------------
    # FUNDO DE RESERVA
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "3. FUNDO DE RESERVA — TRANSFERÊNCIA",
            h2
        )
    )

    fundo = df_mes[
        df_mes["Eh_Fundo"]
    ].copy()

    valor_fundo = fundo[
        "Valor_Absoluto"
    ].sum()

    rows = [
        [
            "Transferência para o Fundo no mês",
            dinheiro(valor_fundo)
        ],
        [
            "Fundo acumulado desde o início do extrato",
            dinheiro(fundo_acumulado)
        ],
        [
            "Tratamento no resultado",
            "NÃO é despesa operacional"
        ],
        [
            "Tratamento no saldo da conta corrente",
            "REDUZ o saldo da conta"
        ]
    ]

    story.append(
        tabela_pdf(
            rows,
            ["Descrição", "Valor / Tratamento"],
            [600, 150]
        )
    )

    story.append(Spacer(1, 12))

    # --------------------------------------------------------
    # CONFERÊNCIA DO SALDO
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "4. CONFERÊNCIA DO SALDO BANCÁRIO",
            h2
        )
    )

    rows = [
        [
            "Arrecadação",
            dinheiro(r["entradas"])
        ],
        [
            "Despesas operacionais",
            dinheiro(r["despesas"])
        ],
        [
            "Transferência para fundo",
            dinheiro(r["fundo"])
        ],
        [
            "Movimento líquido da conta",
            dinheiro(r["movimento_conta"])
        ],
        [
            "Saldo final da conta",
            dinheiro(saldo_final)
        ]
    ]

    story.append(
        tabela_pdf(
            rows,
            ["Item", "Valor"],
            [600, 150]
        )
    )

    story.append(PageBreak())

    # --------------------------------------------------------
    # DETALHAMENTO
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "5. DETALHAMENTO DOS LANÇAMENTOS",
            h2
        )
    )

    detalhes = df_mes.sort_values(
        "Data_Analise"
    )

    rows = []

    for _, linha in detalhes.iterrows():
        data = (
            linha["Data_Analise"].strftime(
                "%d/%m/%Y"
            )
            if pd.notna(linha["Data_Analise"])
            else ""
        )

        categoria = str(
            linha["Categoria"]
        )[:42]

        lanc = (
            str(linha.get(col_lanc, ""))[:70]
            if col_lanc
            else ""
        )

        if linha["Eh_Fundo"]:
            tipo = "TRANSFERÊNCIA FUNDO"
        else:
            tipo = linha["Tipo_Calculado"]

        rows.append([
            data,
            tipo,
            categoria,
            lanc,
            dinheiro(
                linha["Valor_Absoluto"]
            )
        ])

    if rows:
        story.append(
            tabela_pdf(
                rows,
                [
                    "Data",
                    "Tipo",
                    "Categoria",
                    "Lançamento",
                    "Valor"
                ],
                [65, 105, 145, 410, 100]
            )
        )
    else:
        story.append(
            Paragraph(
                "Sem lançamentos.",
                styles["Normal"]
            )
        )

    doc.build(story)

    buffer.seek(0)
    return buffer


# ============================================================
# PDF MENSAL
# ============================================================

with tabs[2]:
    st.subheader("📄 Relatório mensal em PDF")

    if saldos_gerais.empty:
        st.warning(
            "Não há meses disponíveis."
        )
    else:
        meses_pdf = saldos_gerais[
            "Mês"
        ].tolist()

        mes_pdf = st.selectbox(
            "Selecione o mês",
            meses_pdf,
            index=len(meses_pdf) - 1,
            format_func=nome_mes
        )

        df_mes_pdf = df[
            (
                df["Data_Analise"]
                .dt.to_period("M")
                .astype(str)
                == mes_pdf
            )
        ].copy()

        anterior = saldos_gerais[
            saldos_gerais["Mês"] <= mes_pdf
        ]

        fundo_acum = (
            float(
                anterior[
                    "Fundo transferido"
                ].sum()
            )
            if not anterior.empty
            else 0.0
        )

        saldo_mes = float(
            anterior.iloc[-1]["Saldo final"]
        )

        r = resumo_periodo(
            df_mes_pdf
        )

        p1, p2, p3, p4, p5, p6 = st.columns(6)

        p1.metric(
            "Arrecadação",
            dinheiro(r["entradas"])
        )
        p2.metric(
            "Despesas",
            dinheiro(r["despesas"])
        )
        p3.metric(
            "Resultado",
            dinheiro(r["resultado"])
        )
        p4.metric(
            "Fundo no mês",
            dinheiro(r["fundo"])
        )
        p5.metric(
            "Fundo acumulado",
            dinheiro(fundo_acum)
        )
        p6.metric(
            "Saldo conta",
            dinheiro(saldo_mes)
        )

        pdf = gerar_pdf_mensal(
            df_mes_pdf,
            nome_mes(mes_pdf),
            fundo_acum,
            saldo_mes
        )

        st.download_button(
            "⬇️ Baixar relatório PDF",
            data=pdf,
            file_name=(
                f"Relatorio_Mensal_San_Remo_"
                f"{mes_pdf}.pdf"
            ),
            mime="application/pdf"
        )

# ============================================================
# FUNDO DE RESERVA
# ============================================================

with tabs[3]:
    st.subheader("🏦 Fundo de Reserva")

    if fundo_geral.empty:
        st.info(
            "Nenhuma transferência para o Fundo de Reserva "
            "foi identificada."
        )
    else:
        ultimo_fundo = float(
            fundo_geral[
                "Fundo acumulado"
            ].iloc[-1]
        )

        fc1, fc2 = st.columns(2)

        fc1.metric(
            "Fundo acumulado",
            dinheiro(ultimo_fundo)
        )

        fc2.metric(
            "Meses com movimentação",
            len(fundo_geral)
        )

        fig = px.line(
            fundo_geral,
            x="Mês",
            y="Fundo acumulado",
            markers=True,
            title=(
                "Fundo de Reserva acumulado"
            )
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        tabela_fundo = fundo_geral.copy()

        st.dataframe(
            tabela_fundo.style.format({
                "Fundo no mês": dinheiro,
                "Fundo acumulado": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        st.subheader(
            "Movimentações para a aplicação"
        )

        mov_fundo = df[
            df["Eh_Fundo"]
        ].sort_values(
            "Data_Analise"
        )

        colunas_mov = [
            c for c in [
                col_data,
                col_lanc,
                col_razao,
                col_valor,
                "Categoria"
            ]
            if c
        ]

        st.dataframe(
            mov_fundo[colunas_mov],
            use_container_width=True,
            hide_index=True
        )

        st.info(
            "IMPORTANTE: a transferência para o fundo é "
            "positiva no acumulado. Ela não reduz o resultado "
            "operacional, mas reduz o saldo disponível da "
            "conta corrente porque o dinheiro foi aplicado."
        )

# ============================================================
# SALDO BANCÁRIO
# ============================================================

with tabs[4]:
    st.subheader(
        "🏦 Saldo da conta corrente por mês"
    )

    if saldos_gerais.empty:
        st.warning(
            "Não há lançamentos com datas válidas."
        )
    else:
        tabela_saldo = saldos_gerais.copy()

        tabela_saldo["Mês"] = (
            tabela_saldo["Mês"]
            .apply(nome_mes)
        )

        st.dataframe(
            tabela_saldo[[
                "Mês",
                "Data final",
                "Entradas",
                "Despesas",
                "Fundo transferido",
                "Movimento conta corrente",
                "Saldo calculado",
                "Saldo do extrato",
                "Saldo final"
            ]].style.format({
                "Entradas": dinheiro,
                "Despesas": dinheiro,
                "Fundo transferido": dinheiro,
                "Movimento conta corrente": dinheiro,
                "Saldo calculado": dinheiro,
                "Saldo do extrato": dinheiro,
                "Saldo final": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        grafico_saldo = saldos_gerais.copy()

        fig = px.line(
            grafico_saldo,
            x="Mês",
            y="Saldo final",
            markers=True,
            title=(
                "Saldo final da conta corrente "
                "— mês a mês"
            ),
            labels={
                "Saldo final": "Saldo (R$)",
                "Mês": "Mês"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        if col_saldo:
            st.success(
                f"O extrato possui a coluna '{col_saldo}'. "
                "O sistema usa o último saldo disponível de "
                "cada mês como referência e leva esse saldo "
                "para o mês seguinte."
            )
        else:
            st.warning(
                "O extrato não possui uma coluna de saldo "
                "reconhecida. Por isso o sistema calcula o "
                "saldo automaticamente a partir do saldo "
                "inicial informado na lateral."
            )

        st.markdown(
            """
### Regra usada

**Saldo final do mês =**

**Saldo anterior + Arrecadação - Despesas - Fundo de Reserva**

O Fundo de Reserva entra nessa fórmula porque o dinheiro
realmente sai da conta corrente e vai para a aplicação.

Ele, porém, **não entra como despesa operacional**.
"""
        )

# ============================================================
# ARRECADAÇÃO
# ============================================================

with tabs[5]:
    st.subheader(
        "💰 Arrecadação e receitas"
    )

    receitas = df_filtrado[
        df_filtrado["Eh_Receita"]
    ].copy()

    if receitas.empty:
        st.info(
            "Nenhuma receita encontrada com os filtros."
        )
    else:
        resumo_receitas = (
            receitas
            .groupby("Categoria")[
                "Valor_Absoluto"
            ]
            .agg(
                Total="sum",
                Quantidade="size"
            )
            .reset_index()
            .sort_values(
                "Total",
                ascending=False
            )
        )

        st.dataframe(
            resumo_receitas.style.format({
                "Total": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        st.metric(
            "Total de arrecadação",
            dinheiro(
                receitas[
                    "Valor_Absoluto"
                ].sum()
            )
        )

        # Destaque específico das locações.
        antenas = receitas[
            receitas["Categoria"]
            == NOME_ANTENAS
        ]

        st.subheader(
            "📡 Locações de espaço — Antenas"
        )

        if antenas.empty:
            st.info(
                "Nenhuma entrada de Universal Telecom "
                "ou Directnet encontrada."
            )
        else:
            st.metric(
                "Receita de locações",
                dinheiro(
                    antenas[
                        "Valor_Absoluto"
                    ].sum()
                )
            )

            st.dataframe(
                antenas.sort_values(
                    "Data_Analise"
                ),
                use_container_width=True,
                hide_index=True
            )

        st.info(
            "Universal Telecom e Directnet são classificados "
            "como ARRECADAÇÃO de locação de espaço. Eles não "
            "aparecem mais na aba Manutenção."
        )

# ============================================================
# FUNCIONÁRIOS
# ============================================================

with tabs[6]:
    st.subheader("👷 Funcionários")

    f = df_filtrado[
        df_filtrado["Categoria"].str.contains(
            "Salários|Funcionários",
            case=False,
            na=False
        )
    ]

    st.metric(
        "Total de despesas de funcionários",
        dinheiro(
            f["Valor_Absoluto"].sum()
        )
    )

    st.dataframe(
        f.sort_values("Data_Analise"),
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# CONSUMO
# ============================================================

with tabs[7]:
    st.subheader("💡 Contas de consumo")

    f = df_filtrado[
        df_filtrado["Categoria"].str.startswith(
            "Consumo",
            na=False
        )
    ]

    resumo_consumo = (
        f.groupby("Categoria")[
            "Valor_Absoluto"
        ]
        .sum()
        .reset_index()
        .sort_values(
            "Valor_Absoluto",
            ascending=False
        )
    )

    st.dataframe(
        resumo_consumo.style.format({
            "Valor_Absoluto": dinheiro
        }),
        use_container_width=True,
        hide_index=True
    )

    st.dataframe(
        f.sort_values("Data_Analise"),
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# MANUTENÇÃO
# ============================================================

with tabs[8]:
    st.subheader("🛠️ Manutenção")

    categorias_manut = [
        "Manutenção",
        "Elevadores",
        "Segurança Eletrônica",
        "Equipamentos",
        "Obras/Reformas",
        "Jardinagem",
        "Piscina",
    ]

    f = df_filtrado[
        df_filtrado["Categoria"].isin(
            categorias_manut
        )
    ]

    resumo_manut = (
        f.groupby("Categoria")[
            "Valor_Absoluto"
        ]
        .sum()
        .reset_index()
        .sort_values(
            "Valor_Absoluto",
            ascending=False
        )
    )

    st.dataframe(
        resumo_manut.style.format({
            "Valor_Absoluto": dinheiro
        }),
        use_container_width=True,
        hide_index=True
    )

    st.dataframe(
        f.sort_values("Data_Analise"),
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "Antenas de Universal Telecom e Directnet não "
        "ficam nesta aba: são receitas de locação de espaço "
        "e aparecem em Arrecadação."
    )

# ============================================================
# DESPESAS
# ============================================================

with tabs[9]:
    st.subheader("💸 Despesas operacionais")

    s = df_filtrado[
        df_filtrado["Eh_Despesa"]
    ]

    ranking = (
        s.groupby("Categoria")
        .agg(
            Total=("Valor_Absoluto", "sum"),
            Quantidade=("Valor_Absoluto", "size")
        )
        .reset_index()
        .sort_values(
            "Total",
            ascending=False
        )
    )

    st.dataframe(
        ranking.style.format({
            "Total": dinheiro
        }),
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# PESQUISA
# ============================================================

with tabs[10]:
    st.subheader("🔎 Pesquisa detalhada")

    st.dataframe(
        df_filtrado.sort_values(
            "Data_Analise"
        ),
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# CLASSIFICAÇÃO
# ============================================================

with tabs[11]:
    st.subheader(
        "🧠 Classificação automática"
    )

    resumo_class = (
        df.groupby(
            ["Categoria", "Tipo_Calculado"]
        )["Valor_Absoluto"]
        .agg(
            Total="sum",
            Quantidade="size"
        )
        .reset_index()
        .sort_values(
            ["Categoria", "Tipo_Calculado"]
        )
    )

    st.dataframe(
        resumo_class.style.format({
            "Total": dinheiro
        }),
        use_container_width=True,
        hide_index=True
    )

    st.markdown(
        f"""
### Regras especiais

- **Universal Telecom / Directnet → {NOME_ANTENAS}**
- **Aplicação Privilege INT → {NOME_FUNDO}**
- O Fundo de Reserva é acumulado positivamente.
- O Fundo não é despesa operacional.
- O Fundo reduz o saldo da conta corrente.
- O saldo final de um mês é levado para o mês seguinte.
"""
    )

# ============================================================
# DADOS
# ============================================================

with tabs[12]:
    st.subheader("📋 Dados completos")

    st.dataframe(
        df_filtrado.sort_values(
            "Data_Analise"
        ),
        use_container_width=True,
        hide_index=True
    )

    csv_data = df_filtrado.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig"
    )

    st.download_button(
        "⬇️ Baixar CSV filtrado",
        data=csv_data,
        file_name="relatorio_condominio.csv",
        mime="text/csv"
    )

# ============================================================
# RODAPÉ
# ============================================================

st.markdown("---")

st.caption(
    "San Remo • Gestão Financeira Condominial | "
    "Dados atualizados automaticamente via Google Drive."
)
