import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re
import unicodedata
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
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

    # Fundo de reserva:
    # A transferência da conta corrente para a aplicação é tratada
    # como formação/acumulação do fundo, NÃO como despesa econômica.
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

# ============================================================
# FILTROS
# ============================================================
st.sidebar.header("🔍 Filtros avançados")

if st.sidebar.button("🔄 Atualizar dados do Drive"):
    st.cache_data.clear()
    st.rerun()

tipo = st.sidebar.selectbox(
    "Tipo de lançamento",
    ["Todos", "Entrada", "Saída"]
)

categorias_sel = st.sidebar.multiselect(
    "Categoria",
    sorted(df["Categoria"].dropna().unique().tolist())
)

meses_sel = st.sidebar.multiselect(
    "Mês",
    sorted(df["Mes"].dropna().unique().tolist())
)

busca = st.sidebar.text_input(
    "🔎 Pesquisa",
    placeholder="Fornecedor, CNPJ, lançamento..."
)

valor_max = float(df["Valor_Absoluto"].max()) if len(df) else 1.0

faixa = st.sidebar.slider(
    "Faixa de valor (R$)",
    min_value=0.0,
    max_value=max(valor_max, 1.0),
    value=(0.0, max(valor_max, 1.0))
)

somente_func = st.sidebar.checkbox("👷 Somente funcionários")
somente_consumo = st.sidebar.checkbox("💡 Somente consumo")
somente_fundo = st.sidebar.checkbox("🏦 Somente fundo de reserva")

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
    mascara = pd.Series(False, index=df_filtrado.index)

    campos = [
        c for c in [col_lanc, col_razao, col_cnpj]
        if c
    ] + ["Categoria"]

    for c in dict.fromkeys(campos):
        if c in df_filtrado.columns:
            mascara |= df_filtrado[c].astype(str).str.contains(
                busca,
                case=False,
                na=False,
                regex=False
            )

    df_filtrado = df_filtrado[mascara]

df_filtrado = df_filtrado[
    (df_filtrado["Valor_Absoluto"] >= faixa[0]) &
    (df_filtrado["Valor_Absoluto"] <= faixa[1])
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

if somente_fundo:
    df_filtrado = df_filtrado[
        df_filtrado["Categoria"] == NOME_FUNDO
    ]

# ============================================================
# IMPORTANTE:
# TRANSFERÊNCIA PARA FUNDO NÃO É DESPESA DO CONDOMÍNIO.
#
# O extrato bancário mostra:
# Conta corrente: -R$ X
# Investimento: +R$ X
#
# Para o resultado econômico:
# Entrada normal = receita
# Saída normal = despesa
# Fundo = transferência patrimonial/acumulação.
#
# Assim, o fundo é exibido POSITIVO e acumulativo.
# ============================================================

def resumo_periodo(d):
    entradas_normais = d.loc[
        (d["Tipo_Calculado"] == "Entrada") &
        (d["Categoria"] != NOME_FUNDO),
        "Valor_Absoluto"
    ].sum()

    saidas_normais = d.loc[
        (d["Tipo_Calculado"] == "Saída") &
        (d["Categoria"] != NOME_FUNDO),
        "Valor_Absoluto"
    ].sum()

    fundo_acumulado_mes = d.loc[
        d["Categoria"] == NOME_FUNDO,
        "Valor_Absoluto"
    ].sum()

    # Se o fundo for representado no extrato pela saída da conta corrente,
    # o valor absoluto transforma a movimentação em acumulação positiva.
    # Entradas/saídas do próprio fundo são demonstradas separadamente.
    fundo_entradas = d.loc[
        (d["Categoria"] == NOME_FUNDO) &
        (d["Tipo_Calculado"] == "Entrada"),
        "Valor_Absoluto"
    ].sum()

    fundo_saidas = d.loc[
        (d["Categoria"] == NOME_FUNDO) &
        (d["Tipo_Calculado"] == "Saída"),
        "Valor_Absoluto"
    ].sum()

    # Transferência corrente -> investimento deve somar ao fundo.
    fundo_movimentado = fundo_entradas + fundo_saidas

    resultado_operacional = entradas_normais - saidas_normais

    return {
        "entradas": entradas_normais,
        "saidas": saidas_normais,
        "resultado": resultado_operacional,
        "fundo_movimentado": fundo_movimentado,
        "fundo_entradas": fundo_entradas,
        "fundo_saidas": fundo_saidas,
    }

# ============================================================
# SALDO DA CONTA CORRENTE
# ============================================================
# O sistema procura uma coluna de saldo, caso exista no extrato.
# Se não existir, calcula o saldo a partir do saldo inicial configurado.
col_saldo = encontrar_coluna(
    df,
    [
        "saldo",
        "saldo atual",
        "saldo disponível",
        "saldo disponivel",
        "balance"
    ]
)

saldo_inicial_padrao = 0.0

if col_saldo:
    df["Saldo_Extrato"] = limpar_valor(df[col_saldo])
else:
    df["Saldo_Extrato"] = pd.NA

def obter_saldo_fim_mes(d):
    if d.empty:
        return None

    d = d.sort_values("Data_Analise")

    # Se o extrato trouxer saldo, pega o saldo do último lançamento do mês.
    if "Saldo_Extrato" in d.columns and d["Saldo_Extrato"].notna().any():
        validos = d.dropna(subset=["Saldo_Extrato"])
        if not validos.empty:
            return float(validos.iloc[-1]["Saldo_Extrato"])

    # Sem coluna de saldo: cálculo pelo saldo inicial + movimentação.
    # O saldo inicial pode ser informado pelo usuário.
    return None

# ============================================================
# CABEÇALHO
# ============================================================
col_logo, col_titulo = st.columns([1, 5])

with col_logo:
    try:
        st.image("logo.jpg", width=110)
    except Exception:
        st.write("🏢")

with col_titulo:
    st.title("Condomínio Jardim San Remo")
    st.caption(
        "Gestão financeira • Entradas • Saídas • Consumo • "
        "Funcionários • Manutenção • Fundo de Reserva • Saldo bancário"
    )

# ============================================================
# KPIS
# ============================================================
resumo = resumo_periodo(df_filtrado)

# Saldo final disponível no filtro.
saldo_final_extrato = obter_saldo_fim_mes(df_filtrado)

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("💰 Entradas", dinheiro(resumo["entradas"]))
c2.metric("💸 Despesas", dinheiro(resumo["saidas"]))
c3.metric("📈 Resultado operacional", dinheiro(resumo["resultado"]))
c4.metric("🏦 Fundo acumulado", dinheiro(resumo["fundo_movimentado"]))

if saldo_final_extrato is not None:
    c5.metric("🏦 Saldo conta", dinheiro(saldo_final_extrato))
else:
    c5.metric("📋 Lançamentos", f"{len(df_filtrado):,}".replace(",", "."))

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
        d = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()

        if not d.empty:
            d["Ano_Mes"] = d["Data_Analise"].dt.to_period("M").astype(str)

            # Resultado operacional mensal sem transferência para fundo.
            mensal = []

            for mes, grupo in d.groupby("Ano_Mes", sort=True):
                r = resumo_periodo(grupo)
                mensal.append({
                    "Mês": mes,
                    "Entradas": r["entradas"],
                    "Despesas": r["saidas"],
                    "Resultado": r["resultado"],
                    "Fundo": r["fundo_movimentado"]
                })

            mensal_df = pd.DataFrame(mensal)

            comp = mensal_df.melt(
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

            st.subheader("📈 Resultado mensal")

            fig_resultado = px.bar(
                mensal_df,
                x="Mês",
                y="Resultado",
                title="Resultado operacional por mês",
                labels={"Resultado": "Resultado (R$)", "Mês": "Mês"}
            )

            st.plotly_chart(fig_resultado, use_container_width=True)

            st.subheader("🏦 Acumulação do Fundo de Reserva")

            mensal_df["Fundo Acumulado"] = mensal_df["Fundo"].cumsum()

            fig_fundo = px.line(
                mensal_df,
                x="Mês",
                y="Fundo Acumulado",
                markers=True,
                title="Fundo de Reserva acumulado desde janeiro",
                labels={
                    "Fundo Acumulado": "Fundo acumulado (R$)",
                    "Mês": "Mês"
                }
            )

            st.plotly_chart(fig_fundo, use_container_width=True)

        a, b = st.columns(2)

        with a:
            tipo_df = df_filtrado[
                df_filtrado["Categoria"] != NOME_FUNDO
            ].groupby("Tipo_Calculado")["Valor_Absoluto"].sum().reset_index()

            fig = px.pie(
                tipo_df,
                names="Tipo_Calculado",
                values="Valor_Absoluto",
                hole=.45,
                title="Proporção operacional"
            )

            st.plotly_chart(fig, use_container_width=True)

        with b:
            despesas = df_filtrado[
                (df_filtrado["Tipo_Calculado"] == "Saída") &
                (df_filtrado["Categoria"] != NOME_FUNDO)
            ]

            cat = despesas.groupby("Categoria")["Valor_Absoluto"].sum().nlargest(10).sort_values()

            fig = px.bar(
                cat.reset_index(),
                x="Valor_Absoluto",
                y="Categoria",
                orientation="h",
                title="Top 10 despesas"
            )

            st.plotly_chart(fig, use_container_width=True)

# ============================================================
# RELATÓRIO MENSAL
# ============================================================
with tabs[1]:
    st.subheader("📅 Relatório mensal")

    d = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()

    if d.empty:
        st.warning("Não há datas válidas.")
    else:
        d["Ano_Mes"] = d["Data_Analise"].dt.to_period("M").astype(str)

        linhas = []

        for mes, grupo in d.groupby("Ano_Mes", sort=True):
            r = resumo_periodo(grupo)

            saldo_mes = obter_saldo_fim_mes(grupo)

            linhas.append({
                "Mês": mes,
                "Entradas": r["entradas"],
                "Despesas": r["saidas"],
                "Resultado Operacional": r["resultado"],
                "Fundo no mês": r["fundo_movimentado"],
                "Fundo Acumulado": 0.0,
                "Saldo Conta": saldo_mes if saldo_mes is not None else 0.0,
                "Lançamentos": len(grupo)
            })

        mensal = pd.DataFrame(linhas)

        # Acumulação do fundo desde o primeiro mês disponível,
        # normalmente janeiro.
        mensal["Fundo Acumulado"] = mensal["Fundo no mês"].cumsum()

        st.dataframe(
            mensal.style.format({
                "Entradas": dinheiro,
                "Despesas": dinheiro,
                "Resultado Operacional": dinheiro,
                "Fundo no mês": dinheiro,
                "Fundo Acumulado": dinheiro,
                "Saldo Conta": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        st.success(
            "🏦 O Fundo de Reserva agora é positivo e acumulativo: "
            "cada transferência identificada soma ao acumulado, "
            "sem ser tratada como despesa operacional."
        )

# ============================================================
# PDF
# ============================================================
def tabela_pdf(rows, headers, widths):
    tabela = Table(
        [headers] + rows,
        colWidths=widths,
        repeatRows=1
    )

    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#F8FAFC")
        ]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    return tabela

def gerar_pdf_mensal(df_mes, mes_nome, fundo_acumulado):
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
    saldo_mes = obter_saldo_fim_mes(df_mes)

    story = [
        Paragraph(
            "🏢 SAN REMO — RELATÓRIO FINANCEIRO MENSAL",
            titulo
        ),
        Paragraph(
            f"<b>Mês:</b> {mes_nome} &nbsp;&nbsp; "
            f"<b>Emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            subtitulo
        ),
        Spacer(1, 12)
    ]

    # RESUMO
    resumo = [
        [
            "ENTRADAS",
            "DESPESAS",
            "RESULTADO",
            "FUNDO NO MÊS",
            "FUNDO ACUMULADO",
            "SALDO CONTA"
        ],
        [
            dinheiro(r["entradas"]),
            dinheiro(r["saidas"]),
            dinheiro(r["resultado"]),
            dinheiro(r["fundo_movimentado"]),
            dinheiro(fundo_acumulado),
            dinheiro(saldo_mes) if saldo_mes is not None else "N/D"
        ]
    ]

    tabela_resumo = Table(
        resumo,
        colWidths=[120] * 6
    )

    tabela_resumo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#CBD5E1")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story += [
        tabela_resumo,
        Spacer(1, 15)
    ]

    # ENTRADAS
    story.append(Paragraph("1. ENTRADAS", h2))

    entradas = df_mes[
        (df_mes["Tipo_Calculado"] == "Entrada") &
        (df_mes["Categoria"] != NOME_FUNDO)
    ]

    if entradas.empty:
        story.append(Paragraph("Nenhuma entrada no período.", styles["Normal"]))
    else:
        agrupado = (
            entradas.groupby("Categoria")["Valor_Absoluto"]
            .sum()
            .sort_values(ascending=False)
        )

        rows = [
            [str(cat), dinheiro(valor)]
            for cat, valor in agrupado.items()
        ]

        rows.append([
            "TOTAL DE ENTRADAS",
            dinheiro(entradas["Valor_Absoluto"].sum())
        ])

        story.append(
            tabela_pdf(
                rows,
                ["Categoria", "Valor"],
                [600, 150]
            )
        )

    story.append(Spacer(1, 12))

    # DESPESAS
    story.append(Paragraph("2. DESPESAS OPERACIONAIS", h2))

    despesas = df_mes[
        (df_mes["Tipo_Calculado"] == "Saída") &
        (df_mes["Categoria"] != NOME_FUNDO)
    ]

    if despesas.empty:
        story.append(Paragraph("Nenhuma despesa no período.", styles["Normal"]))
    else:
        agrupado = (
            despesas.groupby("Categoria")["Valor_Absoluto"]
            .sum()
            .sort_values(ascending=False)
        )

        rows = [
            [str(cat), dinheiro(valor)]
            for cat, valor in agrupado.items()
        ]

        rows.append([
            "TOTAL DE DESPESAS",
            dinheiro(despesas["Valor_Absoluto"].sum())
        ])

        story.append(
            tabela_pdf(
                rows,
                ["Categoria", "Valor"],
                [600, 150]
            )
        )

    story.append(Spacer(1, 12))

    # FUNDO
    story.append(
        Paragraph(
            "3. FUNDO DE RESERVA — ACUMULAÇÃO",
            h2
        )
    )

    fundo = df_mes[
        df_mes["Categoria"] == NOME_FUNDO
    ].copy()

    if fundo.empty:
        story.append(
            Paragraph(
                "Nenhuma transferência para o fundo identificada.",
                styles["Normal"]
            )
        )
    else:
        valor_fundo = fundo["Valor_Absoluto"].sum()

        rows = [
            ["Movimentação para o Fundo no mês", dinheiro(valor_fundo)],
            ["Fundo acumulado desde janeiro", dinheiro(fundo_acumulado)]
        ]

        story.append(
            tabela_pdf(
                rows,
                ["Descrição", "Valor"],
                [600, 150]
            )
        )

        story.append(Spacer(1, 8))

        mov = fundo.sort_values("Data_Analise")

        rows = []

        for _, linha in mov.iterrows():
            data = (
                linha["Data_Analise"].strftime("%d/%m/%Y")
                if pd.notna(linha["Data_Analise"])
                else ""
            )

            lanc = (
                str(linha.get(col_lanc, ""))[:90]
                if col_lanc
                else ""
            )

            rows.append([
                data,
                "ACUMULAÇÃO",
                lanc,
                dinheiro(linha["Valor_Absoluto"])
            ])

        story.append(
            tabela_pdf(
                rows,
                ["Data", "Tipo", "Lançamento", "Valor"],
                [75, 90, 480, 105]
            )
        )

    # DETALHAMENTO
    story.append(PageBreak())

    story.append(
        Paragraph(
            "4. DETALHAMENTO DOS LANÇAMENTOS",
            h2
        )
    )

    detalhes = df_mes.sort_values("Data_Analise")

    rows = []

    for _, linha in detalhes.iterrows():
        data = (
            linha["Data_Analise"].strftime("%d/%m/%Y")
            if pd.notna(linha["Data_Analise"])
            else ""
        )

        categoria = str(linha["Categoria"])[:38]

        lanc = (
            str(linha.get(col_lanc, ""))[:65]
            if col_lanc
            else ""
        )

        # Fundo aparece como ACUMULAÇÃO, não como despesa.
        tipo = (
            "ACUMULAÇÃO"
            if linha["Categoria"] == NOME_FUNDO
            else linha["Tipo_Calculado"]
        )

        rows.append([
            data,
            tipo,
            categoria,
            lanc,
            dinheiro(linha["Valor_Absoluto"])
        ])

    if rows:
        story.append(
            tabela_pdf(
                rows,
                ["Data", "Tipo", "Categoria", "Lançamento", "Valor"],
                [65, 75, 145, 420, 105]
            )
        )
    else:
        story.append(
            Paragraph("Sem lançamentos.", styles["Normal"])
        )

    doc.build(story)

    buffer.seek(0)
    return buffer

with tabs[2]:
    st.subheader("📄 PDF mensal")

    d_pdf = df_filtrado[
        df_filtrado["Data_Analise"].notna()
    ].copy()

    if d_pdf.empty:
        st.warning("Não há lançamentos com datas válidas.")
    else:
        d_pdf["Ano_Mes"] = (
            d_pdf["Data_Analise"]
            .dt.to_period("M")
            .astype(str)
        )

        meses_pdf = sorted(
            d_pdf["Ano_Mes"].unique(),
            reverse=True
        )

        mes = st.selectbox(
            "Selecione o mês",
            meses_pdf
        )

        df_mes = d_pdf[
            d_pdf["Ano_Mes"] == mes
        ].copy()

        mensal_anterior = d_pdf[
            d_pdf["Ano_Mes"] <= mes
        ]

        fundo_acumulado = resumo_periodo(
            mensal_anterior
        )["fundo_movimentado"]

        r = resumo_periodo(df_mes)

        a, b, c, d, e = st.columns(5)

        a.metric("Entradas", dinheiro(r["entradas"]))
        b.metric("Despesas", dinheiro(r["saidas"]))
        c.metric("Resultado", dinheiro(r["resultado"]))
        d.metric("Fundo no mês", dinheiro(r["fundo_movimentado"]))
        e.metric("Fundo acumulado", dinheiro(fundo_acumulado))

        pdf = gerar_pdf_mensal(
            df_mes,
            mes,
            fundo_acumulado
        )

        st.download_button(
            "⬇️ Baixar relatório PDF",
            data=pdf,
            file_name=f"Relatorio_Mensal_San_Remo_{mes}.pdf",
            mime="application/pdf"
        )

# ============================================================
# FUNDO
# ============================================================
with tabs[3]:
    st.subheader("🏦 Fundo de Reserva")

    fundo = df_filtrado[
        df_filtrado["Categoria"] == NOME_FUNDO
    ].copy()

    # Acumulado desde janeiro do primeiro ano disponível.
    fundo_todos = df[
        df["Categoria"] == NOME_FUNDO
    ].copy()

    if fundo_todos.empty:
        st.info("Nenhuma movimentação de fundo encontrada.")
    else:
        fundo_todos = fundo_todos[
            fundo_todos["Data_Analise"].notna()
        ].copy()

        fundo_todos["Ano_Mes"] = (
            fundo_todos["Data_Analise"]
            .dt.to_period("M")
            .astype(str)
        )

        acumulado = (
            fundo_todos.groupby("Ano_Mes")["Valor_Absoluto"]
            .sum()
            .reset_index()
            .sort_values("Ano_Mes")
        )

        acumulado["Fundo Acumulado"] = (
            acumulado["Valor_Absoluto"].cumsum()
        )

        ultimo = (
            acumulado["Fundo Acumulado"].iloc[-1]
            if not acumulado.empty
            else 0
        )

        a, b = st.columns(2)
        a.metric("🏦 Fundo acumulado", dinheiro(ultimo))
        b.metric("📅 Meses acumulados", len(acumulado))

        fig = px.line(
            acumulado,
            x="Ano_Mes",
            y="Fundo Acumulado",
            markers=True,
            title="Fundo de Reserva acumulado desde janeiro"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        st.dataframe(
            acumulado.style.format({
                "Valor_Absoluto": dinheiro,
                "Fundo Acumulado": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Movimentações")

        st.dataframe(
            fundo.sort_values("Data_Analise"),
            use_container_width=True,
            hide_index=True
        )

        st.info(
            "O valor retirado da conta corrente para a aplicação "
            "é tratado aqui como acumulação patrimonial do fundo, "
            "e não como despesa."
        )

# ============================================================
# SALDO BANCÁRIO
# ============================================================
with tabs[4]:
    st.subheader("🏦 Saldo da conta corrente por mês")

    d_saldo = df[
        df["Data_Analise"].notna()
    ].copy()

    if d_saldo.empty:
        st.warning("Não há datas válidas para calcular o saldo.")
    elif col_saldo:
        d_saldo["Ano_Mes"] = (
            d_saldo["Data_Analise"]
            .dt.to_period("M")
            .astype(str)
        )

        saldo_mensal = (
            d_saldo.sort_values("Data_Analise")
            .groupby("Ano_Mes")
            .tail(1)
            [["Ano_Mes", "Data_Analise", "Saldo_Extrato"]]
            .sort_values("Ano_Mes")
        )

        saldo_mensal = saldo_mensal.rename(
            columns={
                "Ano_Mes": "Mês",
                "Data_Analise": "Último lançamento",
                "Saldo_Extrato": "Saldo final do mês"
            }
        )

        st.dataframe(
            saldo_mensal.style.format({
                "Saldo final do mês": dinheiro
            }),
            use_container_width=True,
            hide_index=True
        )

        fig = px.line(
            saldo_mensal,
            x="Mês",
            y="Saldo final do mês",
            markers=True,
            title="Saldo final da conta corrente"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        st.success(
            "O saldo do último dia/último lançamento de cada mês "
            "é usado como referência para o mês seguinte."
        )

    else:
        st.warning(
            "⚠️ Seu extrato não possui uma coluna de saldo reconhecida. "
            "Por isso o sistema não inventa um saldo bancário."
        )

        st.markdown(
            "Para ativar o saldo automático, o Excel precisa ter uma coluna "
            "como **Saldo**, **Saldo Atual** ou **Saldo Disponível**."
        )

        st.dataframe(
            df[
                [c for c in [
                    col_data,
                    col_lanc,
                    col_valor,
                    col_saldo
                ] if c]
            ].tail(20),
            use_container_width=True,
            hide_index=True
        )

# ============================================================
# FUNCIONÁRIOS
# ============================================================
with tabs[5]:
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
        dinheiro(f["Valor_Absoluto"].sum())
    )

    st.dataframe(
        f.sort_values("Data_Analise"),
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# CONSUMO
# ============================================================
with tabs[6]:
    st.subheader("💡 Contas de consumo")

    f = df_filtrado[
        df_filtrado["Categoria"].str.startswith(
            "Consumo",
            na=False
        )
    ]

    resumo_consumo = (
        f.groupby("Categoria")["Valor_Absoluto"]
        .sum()
        .reset_index()
        .sort_values("Valor_Absoluto", ascending=False)
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
with tabs[7]:
    st.subheader("🛠️ Manutenção")

    f = df_filtrado[
        df_filtrado["Categoria"].str.contains(
            "Manutenção|Elevadores|Segurança Eletrônica|"
            "Obras/Reformas|Jardinagem|Piscina|Antenas",
            case=False,
            na=False
        )
    ]

    resumo_manut = (
        f.groupby("Categoria")["Valor_Absoluto"]
        .sum()
        .reset_index()
        .sort_values("Valor_Absoluto", ascending=False)
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

# ============================================================
# DESPESAS
# ============================================================
with tabs[8]:
    st.subheader("💸 Despesas operacionais")

    s = df_filtrado[
        (df_filtrado["Tipo_Calculado"] == "Saída") &
        (df_filtrado["Categoria"] != NOME_FUNDO)
    ]

    ranking = (
        s.groupby("Categoria")
        .agg(
            Total=("Valor_Absoluto", "sum"),
            Quantidade=("Valor_Absoluto", "size")
        )
        .reset_index()
        .sort_values("Total", ascending=False)
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
with tabs[9]:
    st.subheader("🔎 Pesquisa detalhada")
    st.dataframe(
        df_filtrado.sort_values("Data_Analise"),
        use_container_width=True,
        hide_index=True
    )

# ============================================================
# CLASSIFICAÇÃO
# ============================================================
with tabs[10]:
    st.subheader("🧠 Classificação automática")

    st.dataframe(
        df[
            ["Categoria"]
        ].drop_duplicates().sort_values("Categoria"),
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "A classificação utiliza lançamento, razão social e CNPJ. "
        "A transferência para aplicação Privilege INT é identificada "
        "como Fundo de Reserva."
    )

# ============================================================
# DADOS
# ============================================================
with tabs[11]:
    st.subheader("📋 Dados completos")

    st.dataframe(
        df_filtrado.sort_values("Data_Analise"),
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
