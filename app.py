import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re
import unicodedata
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

# ============================================================
# SAN REMO - GESTÃO FINANCEIRA
# ============================================================
st.set_page_config(
    page_title="San Remo • Gestão Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CONFIGURAÇÕES / FUNÇÕES
# ============================================================
URL_DRIVE = "https://drive.google.com/uc?export=download&id=1DY8-BcxRhWZYPW2rhf07sZBraZk5akTe"
NOME_FUNDO = "Fundo de reserva do condominio"

# VALORES INICIAIS AJUSTADOS (01/01/2026)
SALDO_INICIAL_CONTA_01_01_2026 = 43285.00
SALDO_INICIAL_FUNDO_01_01_2026 = 45881.72

def normalizar_texto(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().lower()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

def dinheiro(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def limpar_valor(serie):
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")

    s = serie.astype(str).str.strip()
    s = s.str.replace("R$", "", regex=False).str.replace(" ", "", regex=False)
    s = s.str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")

def encontrar_coluna(df, nomes):
    mapa = {normalizar_texto(c): c for c in df.columns}

    for nome in nomes:
        chave = normalizar_texto(nome)
        if chave in mapa:
            return mapa[chave]

    for c in df.columns:
        nc = normalizar_texto(c)
        if any(normalizar_texto(n) in nc for n in nomes):
            return c

    return None

# ============================================================
# CLASSIFICAÇÃO
# ============================================================
REGRAS = {
    "Consumo - Água": ["sabesp", "saae", "agua", "saneamento", "esgoto"],
    "Consumo - Energia": ["enel", "edp", "elektro", "energia eletrica", "energia"],
    "Consumo - Gás": ["comgas", "gas natural", "gas encanado", "gas"],
    "Consumo - Telefone/Internet": ["vivo", "claro", "tim", "oi ", "telefonia", "internet", "fibra", "telefon"],

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
        "ferias", "decimo terceiro", "13 salario", "13º", "abono"
    ],
    "Funcionários - Rescisões": [
        "rescisao", "multa fgts", "aviso previo"
    ],

    "Terceirização - Portaria/Segurança": [
        "portaria", "seguranca", "vigilancia",
        "vigia", "controlador de acesso"
    ],
    "Terceirização - Limpeza": [
        "limpeza terceirizada", "conservacao", "asseio", "limpeza"
    ],

    "Administradora": [
        "administradora", "assessoria condominial", "gestao condominial"
    ],
    "Garantidora": [
        "garantidora", "garantia de recebiveis"
    ],

    "Elevadores": [
        "elevador", "elevadores", "qualita", "manutencao elevador"
    ],
    "Manutenção": [
        "manutencao", "conserto", "reparo", "assistencia tecnica"
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
        "intelbras", "cftv", "camera", "alarme", "monitoramento"
    ],
    "Elevadores/Equipamentos": [
        "bomba", "motor", "gerador", "equipamento"
    ],
    "Obras/Reformas": [
        "obra", "reforma", "pintura", "impermeabilizacao", "construcao"
    ],
    "Seguros": [
        "seguro", "apolice"
    ],
    "Impostos/Taxas": [
        "tributo", "imposto", "taxa", "iss", "darf", "prefeitura"
    ],
    "Bancárias": [
        "tarifa bancaria", "tarifa", "banco", "ted", "pix tarifa"
    ],
    "Jurídico": [
        "advogado", "advocacia", "juridico", "processo"
    ],
    "Contabilidade": [
        "contabilidade", "contador", "contabil"
    ],
}

def classificar_linha(row, col_valor, col_lanc, col_cnpj, col_razao):
    txt_lanc = normalizar_texto(row.get(col_lanc, "")) if col_lanc else ""
    txt_cnpj = str(row.get(col_cnpj, "")).strip() if col_cnpj and pd.notna(row.get(col_cnpj)) else ""
    txt_razao = normalizar_texto(row.get(col_razao, "")) if col_razao else ""

    valor = row.get(col_valor, 0)
    tipo = "Entrada" if valor > 0 else ("Saída" if valor < 0 else "Neutro")
    texto = f"{txt_lanc} {txt_razao} {txt_cnpj}".strip()

    if "aplicacao privilege int" in txt_lanc or "privilege int" in txt_lanc:
        return NOME_FUNDO

    if "51877768000189" in re.sub(r"\D", "", txt_cnpj) or \
       "51877768000189" in re.sub(r"\D", "", texto):
        return "Mercadinho"

    if tipo == "Entrada" and abs(valor - 150.0) < 0.01:
        return "Salão de festas"

    if "universal telecom" in texto or "directnet" in texto:
        return "Antenas"

    for categoria, palavras in REGRAS.items():
        if any(normalizar_texto(p) in texto for p in palavras):
            return categoria

    return "Outras Despesas" if tipo == "Saída" else "Receitas"

# ============================================================
# CARREGAMENTO
# ============================================================
@st.cache_data(ttl=300)
def carregar_dados():
    raw = pd.read_excel(URL_DRIVE, header=None)

    linha_cabecalho = 0
    for idx, row in raw.iterrows():
        linha = " ".join(normalizar_texto(v) for v in row.values if pd.notna(v))
        if "valor" in linha or "data" in linha or "lancamento" in linha:
            linha_cabecalho = idx
            break

    return pd.read_excel(URL_DRIVE, header=linha_cabecalho)

try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Não foi possível ler o arquivo do Google Drive: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

col_valor = encontrar_coluna(df, ["valor", "valor r$", "valor (r$)", "amount"])
col_data = encontrar_coluna(df, ["data", "data lançamento", "data lancamento", "date"])
col_lanc = encontrar_coluna(df, ["lançamento", "lancamento", "histórico", "historico"])
col_cnpj = encontrar_coluna(df, ["cpf/cnpj", "cpf", "cnpj", "documento"])
col_razao = encontrar_coluna(df, ["razão social", "razao social", "fornecedor", "favorecido"])

if not col_valor:
    st.error("❌ Não encontrei a coluna de valor.")
    st.write("Colunas encontradas:", list(df.columns))
    st.stop()

df[col_valor] = limpar_valor(df[col_valor])
df = df.dropna(subset=[col_valor]).copy()

if col_data:
    df["Data_Analise"] = pd.to_datetime(df[col_data], dayfirst=True, errors="coerce")
else:
    df["Data_Analise"] = pd.NaT

df["Tipo_Calculado"] = df[col_valor].apply(
    lambda x: "Entrada" if x > 0 else ("Saída" if x < 0 else "Neutro")
)
df["Valor_Absoluto"] = df[col_valor].abs()

df["Categoria"] = df.apply(
    lambda row: classificar_linha(
        row, col_valor, col_lanc, col_cnpj, col_razao
    ),
    axis=1
)

df["Mes"] = df["Data_Analise"].dt.to_period("M").astype(str)
df.loc[df["Mes"] == "NaT", "Mes"] = "Sem data"

col_saldo = encontrar_coluna(
    df,
    ["saldo", "saldo atual", "saldo disponível", "saldo disponivel", "balance"]
)

if col_saldo:
    df["Saldo_Extrato"] = limpar_valor(df[col_saldo])
else:
    df["Saldo_Extrato"] = pd.NA

# ============================================================
# FILTROS E CONFIGURAÇÕES DE BARRA LATERAL
# ============================================================
st.sidebar.header("🔍 Filtros avançados")

if st.sidebar.button("🔄 Atualizar dados do Drive"):
    st.cache_data.clear()
    st.rerun()

saldo_inicial_manual = st.sidebar.number_input(
    "💵 Saldo Inicial Conta (01/01/2026)",
    value=SALDO_INICIAL_CONTA_01_01_2026,
    step=100.0,
    help="Saldo inicial da conta corrente em 01/01/2026."
)

fundo_inicial_manual = st.sidebar.number_input(
    "🏦 Saldo Inicial Fundo Reserva (01/01/2026)",
    value=SALDO_INICIAL_FUNDO_01_01_2026,
    step=100.0,
    help="Saldo inicial do fundo de reserva em 01/01/2026."
)

tipo = st.sidebar.selectbox("Tipo de lançamento", ["Todos", "Entrada", "Saída"])
categorias_sel = st.sidebar.multiselect("Categoria", sorted(df["Categoria"].dropna().unique().tolist()))
meses_sel = st.sidebar.multiselect("Mês", sorted(df["Mes"].dropna().unique().tolist()))
busca = st.sidebar.text_input("🔎 Pesquisa", placeholder="Fornecedor, CNPJ, lançamento...")

valor_max = float(df["Valor_Absoluto"].max()) if len(df) else 1.0
faixa = st.sidebar.slider("Faixa de valor (R$)", min_value=0.0, max_value=max(valor_max, 1.0), value=(0.0, max(valor_max, 1.0)))

somente_func = st.sidebar.checkbox("👷 Somente funcionários")
somente_consumo = st.sidebar.checkbox("💡 Somente consumo")
somente_fundo = st.sidebar.checkbox("🏦 Somente fundo de reserva")

df_filtrado = df.copy()

if tipo != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Tipo_Calculado"] == tipo]
if categorias_sel:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(categorias_sel)]
if meses_sel:
    df_filtrado = df_filtrado[df_filtrado["Mes"].isin(meses_sel)]

if busca:
    mascara = pd.Series(False, index=df_filtrado.index)
    campos = [c for c in [col_lanc, col_razao, col_cnpj] if c] + ["Categoria"]
    for c in dict.fromkeys(campos):
        if c in df_filtrado.columns:
            mascara |= df_filtrado[c].astype(str).str.contains(busca, case=False, na=False, regex=False)
    df_filtrado = df_filtrado[mascara]

df_filtrado = df_filtrado[
    (df_filtrado["Valor_Absoluto"] >= faixa[0]) &
    (df_filtrado["Valor_Absoluto"] <= faixa[1])
]

if somente_func:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)]
if somente_consumo:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].str.startswith("Consumo", na=False)]
if somente_fundo:
    df_filtrado = df_filtrado[df_filtrado["Categoria"] == NOME_FUNDO]

# ============================================================
# LÓGICA DE TRANSPOSIÇÃO DE SALDO E CÁLCULOS (CORRIGIDA)
# ============================================================
def resumo_periodo(d):
    entradas_normais = d.loc[(d["Tipo_Calculado"] == "Entrada") & (d["Categoria"] != NOME_FUNDO), "Valor_Absoluto"].sum()
    saidas_normais = d.loc[(d["Tipo_Calculado"] == "Saída") & (d["Categoria"] != NOME_FUNDO), "Valor_Absoluto"].sum()

    fundo_saida_conta = d.loc[(d["Categoria"] == NOME_FUNDO) & (d["Tipo_Calculado"] == "Saída"), "Valor_Absoluto"].sum()
    fundo_entrada_conta = d.loc[(d["Categoria"] == NOME_FUNDO) & (d["Tipo_Calculado"] == "Entrada"), "Valor_Absoluto"].sum()

    fundo_movimentado_liquido = fundo_saida_conta - fundo_entrada_conta
    resultado_operacional = entradas_normais - saidas_normais

    total_entradas_conta = entradas_normais + fundo_entrada_conta
    total_saidas_conta = saidas_normais + fundo_saida_conta

    return {
        "entradas": entradas_normais,
        "saidas": saidas_normais,
        "resultado": resultado_operacional,
        "fundo_movimentado": fundo_movimentado_liquido,
        "fundo_saida_conta": fundo_saida_conta,
        "fundo_entrada_conta": fundo_entrada_conta,
        "total_entradas_conta": total_entradas_conta,
        "total_saidas_conta": total_saidas_conta
    }

def calcular_cronograma_mensal(df_completo, saldo_inicial_start=43285.00, fundo_inicial_start=45881.72):
    d = df_completo[df_completo["Data_Analise"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    d["Ano_Mes"] = d["Data_Analise"].dt.to_period("M").astype(str)
    meses_ordenados = sorted(d["Ano_Mes"].unique())

    linhas = []
    saldo_anterior = saldo_inicial_start
    fundo_acumulado_prev = fundo_inicial_start

    for idx, mes in enumerate(meses_ordenados):
        grupo = d[d["Ano_Mes"] == mes].sort_values("Data_Analise")
        r = resumo_periodo(grupo)

        saldo_ini_mes = saldo_anterior
        
        saldo_fim_mes = saldo_ini_mes + r["total_entradas_conta"] - r["total_saidas_conta"]
        fundo_acumulado_mes = fundo_acumulado_prev + r["fundo_movimentado"]

        linhas.append({
            "Mês": mes,
            "Saldo Inicial": saldo_ini_mes,
            "Entradas": r["entradas"],
            "Despesas": r["saidas"],
            "Resultado Operacional": r["resultado"],
            "Fundo no mês": r["fundo_movimentado"],
            "Fundo Acumulado": fundo_acumulado_mes,
            "Saldo Final": saldo_fim_mes,
            "Lançamentos": len(grupo)
        })

        saldo_anterior = saldo_fim_mes
        fundo_acumulado_prev = fundo_acumulado_mes

    df_mensal = pd.DataFrame(linhas)
    return df_mensal

# ============================================================
# CABEÇALHO E KPIS
# ============================================================
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    try:
        st.image("logo.jpg", width=110)
    except Exception:
        st.write("🏢")

with col_titulo:
    st.title("Condomínio Jardim San Remo")
    st.caption("Gestão financeira • Entradas • Saídas • Consumo • Funcionários • Manutenção • Fundo de Reserva • Saldo bancário")

resumo = resumo_periodo(df_filtrado)

df_mensal_calc = calcular_cronograma_mensal(df, saldo_inicial_manual, fundo_inicial_manual)

if meses_sel:
    df_mensal_calc_filtrado = df_mensal_calc[df_mensal_calc["Mês"].isin(meses_sel)]
else:
    df_mensal_calc_filtrado = df_mensal_calc

saldo_atual_exibicao = df_mensal_calc_filtrado["Saldo Final"].iloc[-1] if not df_mensal_calc_filtrado.empty else 0.0
fundo_atual_exibicao = df_mensal_calc_filtrado["Fundo Acumulado"].iloc[-1] if not df_mensal_calc_filtrado.empty else 0.0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Entradas", dinheiro(resumo["entradas"]))
c2.metric("💸 Despesas", dinheiro(resumo["saidas"]))
c3.metric("📈 Resultado operacional", dinheiro(resumo["resultado"]))
c4.metric("🏦 Fundo Acumulado", dinheiro(fundo_atual_exibicao))
c5.metric("🏦 Saldo Final Atual", dinheiro(saldo_atual_exibicao))

# ============================================================
# ABAS
# ============================================================
tabs = st.tabs([
    "📊 Dashboard",
    "📅 Relatório Mensal",
    "📄 PDF Mensal",
    "🏦 Fundo de Reserva",
    "🏦 Saldo Bancário",
    "👷 Funcionários",
    "💡 Consumo",
    "🛠️ Manutenção",
    "💸 Despesas",
    "🔎 Pesquisa",
    "🧠 Classificação",
    "📋 Dados"
])

# ============================================================
# DASHBOARD
# ============================================================
with tabs[0]:
    st.subheader("📊 Dashboard financeiro")
    if df_filtrado.empty:
        st.warning("Nenhum lançamento corresponde aos filtros.")
    else:
        if not df_mensal_calc_filtrado.empty:
            comp = df_mensal_calc_filtrado.melt(
                id_vars=["Mês"],
                value_vars=["Entradas", "Despesas"],
                var_name="Tipo",
                value_name="Valor"
            )

            fig = px.bar(
                comp,
                x="Mês",
                y="Valor",
                color="Tipo",
                barmode="group",
                title="📊 Entradas x Despesas — resultado operacional",
                labels={"Mês": "Mês", "Valor": "Valor (R$)", "Tipo": ""}
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📈 Resultado e Evolução de Saldo Mensal")
            fig_resultado = px.line(
                df_mensal_calc_filtrado,
                x="Mês",
                y=["Saldo Inicial", "Saldo Final"],
                markers=True,
                title="Transposição de Saldos Mês a Mês"
            )
            st.plotly_chart(fig_resultado, use_container_width=True)

            st.subheader("🏦 Acumulação do Fundo de Reserva")
            fig_fundo = px.line(
                df_mensal_calc_filtrado,
                x="Mês",
                y="Fundo Acumulado",
                markers=True,
                title="Evolução do Fundo de Reserva Acumulado"
            )
            st.plotly_chart(fig_fundo, use_container_width=True)

        a, b = st.columns(2)
        with a:
            tipo_df = df_filtrado[df_filtrado["Categoria"] != NOME_FUNDO].groupby("Tipo_Calculado")["Valor_Absoluto"].sum().reset_index()
            fig = px.pie(tipo_df, names="Tipo_Calculado", values="Valor_Absoluto", hole=.45, title="Proporção operacional")
            st.plotly_chart(fig, use_container_width=True)

        with b:
            despesas = df_filtrado[(df_filtrado["Tipo_Calculado"] == "Saída") & (df_filtrado["Categoria"] != NOME_FUNDO)]
            cat = despesas.groupby("Categoria")["Valor_Absoluto"].sum().nlargest(10).sort_values()
            fig = px.bar(cat.reset_index(), x="Valor_Absoluto", y="Categoria", orientation="h", title="Top 10 despesas")
            st.plotly_chart(fig, use_container_width=True)

# ============================================================
# RELATÓRIO MENSAL (TRANSPOSIÇÃO DE SALDOS)
# ============================================================
with tabs[1]:
    st.subheader("📅 Relatório mensal com Transposição de Saldo")

    df_mensal_rel = calcular_cronograma_mensal(df, saldo_inicial_manual, fundo_inicial_manual)

    if meses_sel:
        df_mensal_rel = df_mensal_rel[df_mensal_rel["Mês"].isin(meses_sel)]

    if df_mensal_rel.empty:
        st.warning("Não há datas válidas para o relatório.")
    else:
        st.dataframe(
            df_mensal_rel.style.format({
                "Saldo Inicial": dinheiro,
                "Entradas": dinheiro,
                "Despesas": dinheiro,
                "Resultado Operacional": dinheiro,
                "Fundo no mês": dinheiro,
                "Fundo Acumulado": dinheiro,
                "Saldo Final": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

# ============================================================
# PDF
# ============================================================
def tabela_pdf(rows, headers, widths):
    tabela = Table([headers] + rows, colWidths=widths, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tabela

def gerar_pdf_mensal(df_mes, mes_nome, dados_mes):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()

    titulo = ParagraphStyle("Titulo", parent=styles["Heading1"], fontSize=18, leading=21, alignment=TA_CENTER, textColor=colors.HexColor("#1E3A8A"))
    subtitulo = ParagraphStyle("Subtitulo", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#1E3A8A"))

    r = resumo_periodo(df_mes)

    story = [
        Paragraph("🏢 SAN REMO — RELATÓRIO FINANCEIRO MENSAL", titulo),
        Paragraph(f"<b>Mês:</b> {mes_nome} &nbsp;&nbsp; <b>Emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitulo),
        Spacer(1, 12)
    ]

    resumo_tbl = [
        ["SALDO INICIAL", "ENTRADAS", "DESPESAS", "RESULTADO", "FUNDO ACUM.", "SALDO FINAL"],
        [
            dinheiro(dados_mes["Saldo Inicial"]),
            dinheiro(r["entradas"]),
            dinheiro(r["saidas"]),
            dinheiro(r["resultado"]),
            dinheiro(dados_mes["Fundo Acumulado"]),
            dinheiro(dados_mes["Saldo Final"])
        ]
    ]

    tabela_resumo = Table(resumo_tbl, colWidths=[120] * 6)
    tabela_resumo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#CBD5E1")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story += [tabela_resumo, Spacer(1, 15)]

    # ENTRADAS
    story.append(Paragraph("1. ENTRADAS", h2))
    entradas = df_mes[(df_mes["Tipo_Calculado"] == "Entrada") & (df_mes["Categoria"] != NOME_FUNDO)]

    if entradas.empty:
        story.append(Paragraph("Nenhuma entrada no período.", styles["Normal"]))
    else:
        agrupado = entradas.groupby("Categoria")["Valor_Absoluto"].sum().sort_values(ascending=False)
        rows = [[str(cat), dinheiro(valor)] for cat, valor in agrupado.items()]
        rows.append(["TOTAL DE ENTRADAS", dinheiro(entradas["Valor_Absoluto"].sum())])
        story.append(tabela_pdf(rows, ["Categoria", "Valor"], [600, 150]))

    story.append(Spacer(1, 12))

    # DESPESAS
    story.append(Paragraph("2. DESPESAS OPERACIONAIS", h2))
    despesas = df_mes[(df_mes["Tipo_Calculado"] == "Saída") & (df_mes["Categoria"] != NOME_FUNDO)]

    if despesas.empty:
        story.append(Paragraph("Nenhuma despesa no período.", styles["Normal"]))
    else:
        agrupado = despesas.groupby("Categoria")["Valor_Absoluto"].sum().sort_values(ascending=False)
        rows = [[str(cat), dinheiro(valor)] for cat, valor in agrupado.items()]
        rows.append(["TOTAL DE DESPESAS", dinheiro(despesas["Valor_Absoluto"].sum())])
        story.append(tabela_pdf(rows, ["Categoria", "Valor"], [600, 150]))

    doc.build(story)
    buffer.seek(0)
    return buffer

with tabs[2]:
    st.subheader("📄 PDF mensal")
    df_m = calcular_cronograma_mensal(df, saldo_inicial_manual, fundo_inicial_manual)

    if df_m.empty:
        st.warning("Não há lançamentos para gerar PDF.")
    else:
        mes_sel_pdf = st.selectbox("Selecione o mês", df_m["Mês"].tolist(), index=len(df_m)-1)
        dados_mes_sel = df_m[df_m["Mês"] == mes_sel_pdf].iloc[0]

        df_mes_dados = df[df["Mes"] == mes_sel_pdf]

        pdf_buf = gerar_pdf_mensal(df_mes_dados, mes_sel_pdf, dados_mes_sel)

        st.download_button(
            "⬇️ Baixar relatório PDF Mensal",
            data=pdf_buf,
            file_name=f"Relatorio_Mensal_{mes_sel_pdf}.pdf",
            mime="application/pdf"
        )

# ============================================================
# FUNDO DE RESERVA
# ============================================================
with tabs[3]:
    st.subheader("🏦 Fundo de Reserva")
    fundo = df_filtrado[df_filtrado["Categoria"] == NOME_FUNDO].copy()
    if fundo.empty:
        st.info("Nenhuma movimentação de fundo encontrada.")
    else:
        st.dataframe(fundo.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

# ============================================================
# SALDO BANCÁRIO / TRANSPOSIÇÃO
# ============================================================
with tabs[4]:
    st.subheader("🏦 Saldo Bancário e Transposição Mês a Mês")

    df_saldo_tab = calcular_cronograma_mensal(df, saldo_inicial_manual, fundo_inicial_manual)

    if meses_sel:
        df_saldo_tab = df_saldo_tab[df_saldo_tab["Mês"].isin(meses_sel)]

    if not df_saldo_tab.empty:
        st.dataframe(
            df_saldo_tab[["Mês", "Saldo Inicial", "Resultado Operacional", "Fundo no mês", "Fundo Acumulado", "Saldo Final"]].style.format({
                "Saldo Inicial": dinheiro,
                "Resultado Operacional": dinheiro,
                "Fundo no mês": dinheiro,
                "Fundo Acumulado": dinheiro,
                "Saldo Final": dinheiro,
            }),
            use_container_width=True,
            hide_index=True
        )

        fig = px.bar(
            df_saldo_tab,
            x="Mês",
            y=["Saldo Inicial", "Saldo Final"],
            barmode="group",
            title="Comparativo Saldo Inicial vs Saldo Final por Mês"
        )
        st.plotly_chart(fig, use_container_width=True)

# ============================================================
# DEMAIS ABAS
# ============================================================
with tabs[5]:
    st.subheader("👷 Funcionários")
    st.dataframe(df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)], use_container_width=True, hide_index=True)

with tabs[6]:
    st.subheader("💡 Contas de consumo")
    st.dataframe(df_filtrado[df_filtrado["Categoria"].str.startswith("Consumo", na=False)], use_container_width=True, hide_index=True)

with tabs[7]:
    st.subheader("🛠️ Manutenção")
    st.dataframe(df_filtrado[df_filtrado["Categoria"].str.contains("Manutenção|Elevadores|Segurança|Obras|Jardinagem|Piscina", case=False, na=False)], use_container_width=True, hide_index=True)

with tabs[8]:
    st.subheader("💸 Despesas operacionais")
    st.dataframe(df_filtrado[(df_filtrado["Tipo_Calculado"] == "Saída") & (df_filtrado["Categoria"] != NOME_FUNDO)], use_container_width=True, hide_index=True)

with tabs[9]:
    st.subheader("🔎 Pesquisa detalhada")
    st.dataframe(df_filtrado.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

with tabs[10]:
    st.subheader("🧠 Classificação automática")
    st.dataframe(df[["Categoria"]].drop_duplicates().sort_values("Categoria"), use_container_width=True, hide_index=True)

with tabs[11]:
    st.subheader("📋 Dados completos")
    st.dataframe(df_filtrado.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

# ============================================================
# RODAPÉ
# ============================================================
st.markdown("---")
st.caption("San Remo • Gestão Financeira Condominial | Correção de transposição aplicada.")