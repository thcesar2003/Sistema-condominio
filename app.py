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
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

# ============================================================
# CONFIGURAÇÃO
# ============================================================
st.set_page_config(
    page_title="San Remo • Gestão Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.metric-card {
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    background: #fafafa;
}
.small-note { color:#6b7280; font-size:0.85rem; }
</style>
""", unsafe_allow_html=True)

col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    try:
        st.image("logo.jpg", width=110)
    except Exception:
        st.write("🏢")
with col_titulo:
    st.title("Condomínio Jardim San Remo")
    st.caption("Gestão financeira • entradas • saídas • consumo • funcionários • manutenção • fundo de reserva")

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
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
    # Detecta formatos brasileiros e negativos.
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    s = s.str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
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
    "Salários": ["salario", "folha", "pagamento funcionario", "pagamento de funcionario", "pro labore", "pro-labore"],
    "Funcionários - Encargos": ["fgts", "inss", "gps", "e-social", "esocial", "irrf", "contribuicao previdenciaria"],
    "Funcionários - Benefícios": ["vale transporte", "vt ", "vale refeicao", "vale alimentacao", "alelo", "ticket", "cesta basica", "beneficio"],
    "Funcionários - Férias/13º": ["ferias", "decimo terceiro", "13 salario", "13º", "abono"],
    "Funcionários - Rescisões": ["rescisao", "multa fgts", "aviso previo"],
    "Terceirização - Portaria/Segurança": ["portaria", "seguranca", "vigilancia", "vigia", "controlador de acesso"],
    "Terceirização - Limpeza": ["limpeza terceirizada", "conservacao", "asseio", "limpeza"],
    "Administradora": ["administradora", "assessoria condominial", "gestao condominial"],
    "Garantidora": ["garantidora", "garantia de recebiveis"],
    "Elevadores": ["elevador", "elevadores", "qualita", "manutencao elevador"],
    "Manutenção": ["manutencao", "conserto", "reparo", "assistencia tecnica"],
    "Limpeza/Material": ["material de limpeza", "produto de limpeza", "detergente", "desinfetante", "saco de lixo"],
    "Jardinagem": ["jardinagem", "jardim", "paisagismo", "poda"],
    "Piscina": ["piscina", "cloro", "tratamento piscina"],
    "Segurança Eletrônica": ["intelbras", "cftv", "camera", "alarme", "monitoramento"],
    "Elevadores/Equipamentos": ["bomba", "motor", "gerador", "equipamento"],
    "Obras/Reformas": ["obra", "reforma", "pintura", "impermeabilizacao", "construcao"],
    "Seguros": ["seguro", "apolice"],
    "Impostos/Taxas": ["tributo", "imposto", "taxa", "iss", "darf", "prefeitura"],
    "Bancárias": ["tarifa bancaria", "tarifa", "banco", "ted", "pix tarifa"],
    "Jurídico": ["advogado", "advocacia", "juridico", "processo"],
    "Contabilidade": ["contabilidade", "contador", "contabil"],
}

def classificar_linha(row, col_valor, col_lanc, col_cnpj, col_razao):
    txt_lanc = normalizar_texto(row.get(col_lanc, "")) if col_lanc else ""
    txt_cnpj_bruto = str(row.get(col_cnpj, "")).strip() if col_cnpj and pd.notna(row.get(col_cnpj)) else ""
    txt_cnpj_limpo = re.sub(r"\D", "", txt_cnpj_bruto)
    txt_razao = normalizar_texto(row.get(col_razao, "")) if col_razao else ""
    valor = row.get(col_valor, 0)
    tipo = "Entrada" if valor > 0 else ("Saída" if valor < 0 else "Neutro")
    texto = f"{txt_lanc} {txt_razao} {txt_cnpj_bruto}".strip()

    if "aplicacao privilege int" in txt_lanc or "privilege int" in txt_lanc:
        return "Fundo de reserva do condominio"
    if "51877768000189" in txt_cnpj_limpo or "51877768000189" in re.sub(r"\D", "", texto):
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
# GOOGLE DRIVE
# ============================================================
url = "https://drive.google.com/uc?export=download&id=1DY8-BcxRhWZYPW2rhf07sZBraZk5akTe"

@st.cache_data(ttl=300)
def carregar_dados():
    raw = pd.read_excel(url, header=None)
    cab = 0
    for idx, row in raw.iterrows():
        linha = " ".join(normalizar_texto(v) for v in row.values if pd.notna(v))
        if "valor" in linha or "data" in linha or "lancamento" in linha:
            cab = idx
            break
    return pd.read_excel(url, header=cab)

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
    st.error("❌ Não encontrei a coluna de valor. Renomeie a coluna para 'Valor'.")
    st.write("Colunas encontradas:", list(df.columns))
    st.stop()

df[col_valor] = limpar_valor(df[col_valor])
df = df.dropna(subset=[col_valor]).copy()
df["Data_Analise"] = pd.to_datetime(df[col_data], dayfirst=True, errors="coerce") if col_data else pd.NaT
df["Tipo_Calculado"] = df[col_valor].apply(lambda x: "Entrada" if x > 0 else ("Saída" if x < 0 else "Neutro"))
df["Valor_Absoluto"] = df[col_valor].abs()

df["Categoria"] = df.apply(
    lambda row: classificar_linha(row, col_valor, col_lanc, col_cnpj, col_razao), axis=1
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

tipo = st.sidebar.selectbox("Tipo de lançamento", ["Todos", "Entrada", "Saída"])
categorias = sorted(df["Categoria"].dropna().unique().tolist())
categorias_sel = st.sidebar.multiselect("Categoria", categorias)
meses = sorted(df["Mes"].dropna().unique().tolist())
meses_sel = st.sidebar.multiselect("Mês", meses)

busca = st.sidebar.text_input("🔎 Pesquisa geral", placeholder="Fornecedor, CNPJ, lançamento...")

valor_max = float(df["Valor_Absoluto"].max()) if len(df) else 1.0
faixa = st.sidebar.slider("Faixa de valor (R$)", 0.0, max(valor_max, 1.0), (0.0, max(valor_max, 1.0)))

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
    df_filtrado = df_filtrado[df_filtrado["Categoria"] == "Fundo de reserva do condominio"]

# ============================================================
# FUNDO DE RESERVA — TRATAMENTO SEPARADO
# ============================================================
def resumo_financeiro(d):
    entradas = d.loc[d["Tipo_Calculado"] == "Entrada", "Valor_Absoluto"].sum()
    saidas = d.loc[d["Tipo_Calculado"] == "Saída", "Valor_Absoluto"].sum()
    fundo_entradas = d.loc[
        (d["Categoria"] == "Fundo de reserva do condominio") &
        (d["Tipo_Calculado"] == "Entrada"), "Valor_Absoluto"
    ].sum()
    fundo_saidas = d.loc[
        (d["Categoria"] == "Fundo de reserva do condominio") &
        (d["Tipo_Calculado"] == "Saída"), "Valor_Absoluto"
    ].sum()
    return {
        "entradas": entradas,
        "saidas": saidas,
        "resultado": entradas - saidas,
        "fundo_entradas": fundo_entradas,
        "fundo_saidas": fundo_saidas,
        "fundo_resultado": fundo_entradas - fundo_saidas,
    }

k = resumo_financeiro(df_filtrado)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Entradas", dinheiro(k["entradas"]))
c2.metric("💸 Saídas", dinheiro(k["saidas"]))
c3.metric("📈 Resultado", dinheiro(k["resultado"]))
c4.metric("🏦 Fundo de reserva", dinheiro(k["fundo_resultado"]))
c5.metric("📋 Lançamentos", f"{len(df_filtrado):,}".replace(",", "."))

# ============================================================
# PDF MENSAL — ESTRUTURA NOVA E ORGANIZADA
# ============================================================
def tabela_pdf(data, headers, widths):
    t = Table([headers] + data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (-1,1), (-1,-1), "RIGHT"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    return t

def gerar_pdf_mensal(df_mes, mes_nome):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "Titulo", parent=styles["Heading1"], fontSize=18, leading=21,
        alignment=TA_CENTER, textColor=colors.HexColor("#1E3A8A")
    )
    subtitulo = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#4B5563")
    )
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#1E3A8A"))

    r = resumo_financeiro(df_mes)
    story = [
        Paragraph("🏢 SAN REMO — RELATÓRIO FINANCEIRO MENSAL", titulo),
        Paragraph(
            f"<b>Mês de referência:</b> {mes_nome} &nbsp;&nbsp; "
            f"<b>Emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            subtitulo
        ),
        Spacer(1, 12),
    ]

    # Resumo principal
    resumo = [
        ["ENTRADAS", "SAÍDAS", "RESULTADO", "ENTRADAS FUNDO", "SAÍDAS FUNDO", "RESULTADO FUNDO"],
        [dinheiro(r["entradas"]), dinheiro(r["saidas"]), dinheiro(r["resultado"]),
         dinheiro(r["fundo_entradas"]), dinheiro(r["fundo_saidas"]), dinheiro(r["fundo_resultado"])]
    ]
    tr = Table(resumo, colWidths=[125]*6)
    tr.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F3F4F6")),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),
        ("FONTSIZE",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),7),
        ("BOTTOMPADDING",(0,0),(-1,-1),7),
    ]))
    story += [tr, Spacer(1, 14)]

    # Entradas
    story.append(Paragraph("1. ENTRADAS", h2))
    ent = df_mes[df_mes["Tipo_Calculado"] == "Entrada"].copy()
    if ent.empty:
        story.append(Paragraph("Nenhuma entrada no período.", styles["Normal"]))
    else:
        ent_cat = ent.groupby("Categoria")["Valor_Absoluto"].sum().sort_values(ascending=False)
        rows = [[str(c), dinheiro(v)] for c, v in ent_cat.items()]
        rows.append(["TOTAL DE ENTRADAS", dinheiro(ent["Valor_Absoluto"].sum())])
        story.append(tabela_pdf(rows, ["Categoria", "Valor"], [600, 150]))
    story.append(Spacer(1, 12))

    # Saídas
    story.append(Paragraph("2. SAÍDAS / DESPESAS", h2))
    sai = df_mes[df_mes["Tipo_Calculado"] == "Saída"].copy()
    if sai.empty:
        story.append(Paragraph("Nenhuma saída no período.", styles["Normal"]))
    else:
        sai_cat = sai.groupby("Categoria")["Valor_Absoluto"].sum().sort_values(ascending=False)
        rows = [[str(c), dinheiro(v)] for c, v in sai_cat.items()]
        rows.append(["TOTAL DE SAÍDAS", dinheiro(sai["Valor_Absoluto"].sum())])
        story.append(tabela_pdf(rows, ["Categoria", "Valor"], [600, 150]))
    story.append(Spacer(1, 12))

    # Fundo de reserva isolado
    story.append(Paragraph("3. FUNDO DE RESERVA — MOVIMENTAÇÃO SEPARADA", h2))
    fundo = df_mes[df_mes["Categoria"] == "Fundo de reserva do condominio"].copy()
    if fundo.empty:
        story.append(Paragraph("Nenhuma movimentação identificada como fundo de reserva no período.", styles["Normal"]))
    else:
        fe = fundo[fundo["Tipo_Calculado"] == "Entrada"]["Valor_Absoluto"].sum()
        fs = fundo[fundo["Tipo_Calculado"] == "Saída"]["Valor_Absoluto"].sum()
        fr = fe - fs
        fundo_resumo = [
            ["Entradas do fundo", dinheiro(fe)],
            ["Saídas do fundo", dinheiro(fs)],
            ["Resultado do fundo no mês", dinheiro(fr)],
        ]
        story.append(tabela_pdf(fundo_resumo, ["Movimentação", "Valor"], [600,150]))
        story.append(Spacer(1, 8))
        mov = fundo.sort_values("Data_Analise")
        rows = []
        for _, x in mov.iterrows():
            data = x["Data_Analise"].strftime("%d/%m/%Y") if pd.notna(x["Data_Analise"]) else ""
            lanc = str(x.get(col_lanc, ""))[:80] if col_lanc else ""
            rows.append([data, x["Tipo_Calculado"], lanc, dinheiro(x["Valor_Absoluto"])])
        story.append(tabela_pdf(rows, ["Data", "Tipo", "Lançamento", "Valor"], [75,80,480,115]))

    # Detalhamento completo no final
    story.append(PageBreak())
    story.append(Paragraph("4. LANÇAMENTOS DO MÊS — DETALHAMENTO", h2))
    detalhes = df_mes.sort_values(["Data_Analise", "Tipo_Calculado"]).copy()
    rows = []
    for _, x in detalhes.iterrows():
        data = x["Data_Analise"].strftime("%d/%m/%Y") if pd.notna(x["Data_Analise"]) else ""
        lanc = str(x.get(col_lanc, ""))[:65] if col_lanc else ""
        cat = str(x["Categoria"])[:38]
        rows.append([data, x["Tipo_Calculado"], cat, lanc, dinheiro(x["Valor_Absoluto"])])

    if rows:
        story.append(tabela_pdf(
            rows,
            ["Data", "Tipo", "Categoria", "Lançamento", "Valor"],
            [65,65,145,430,100]
        ))
    else:
        story.append(Paragraph("Sem lançamentos.", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ============================================================
# ABAS
# ============================================================
tabs = st.tabs([
    "📊 Dashboard", "📅 Relatório Mensal", "📄 PDF Mensal",
    "👷 Funcionários", "💡 Consumo", "🛠️ Manutenção",
    "💸 Despesas", "🏦 Fundo de Reserva", "🔎 Pesquisa",
    "🧠 Classificação", "📋 Dados"
])

# ============================================================
# DASHBOARD
# ============================================================
with tabs[0]:
    st.subheader("📊 Visão Geral Financeira")

    if df_filtrado.empty:
        st.warning("Nenhum lançamento corresponde aos filtros.")
    else:
        d = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()
        if not d.empty:
            d["Ano_Mes"] = d["Data_Analise"].dt.to_period("M").astype(str)
            comp = d.groupby(["Ano_Mes","Tipo_Calculado"])["Valor_Absoluto"].sum().reset_index()
            fig = px.bar(
                comp, x="Ano_Mes", y="Valor_Absoluto", color="Tipo_Calculado",
                barmode="group", title="📊 Entradas x Saídas por mês",
                labels={"Ano_Mes":"Mês","Valor_Absoluto":"Valor (R$)","Tipo_Calculado":"Tipo"},
                color_discrete_map={"Entrada":"#10B981","Saída":"#EF4444"}
            )
            fig.update_layout(xaxis_type="category", height=400)
            st.plotly_chart(fig, use_container_width=True)

        a, b = st.columns(2)
        with a:
            tipo_df = df_filtrado.groupby("Tipo_Calculado")["Valor_Absoluto"].sum().reset_index()
            fig = px.pie(
                tipo_df, names="Tipo_Calculado", values="Valor_Absoluto",
                hole=.45, title="Proporção Entradas x Saídas",
                color="Tipo_Calculado",
                color_discrete_map={"Entrada":"#10B981","Saída":"#EF4444","Neutro":"#6B7280"}
            )
            st.plotly_chart(fig, use_container_width=True)
        with b:
            cat = df_filtrado[df_filtrado["Tipo_Calculado"]=="Saída"].groupby("Categoria")["Valor_Absoluto"].sum().nlargest(10).sort_values()
            fig = px.bar(
                cat.reset_index(), x="Valor_Absoluto", y="Categoria",
                orientation="h", title="Top 10 despesas por categoria",
                labels={"Valor_Absoluto":"Valor (R$)","Categoria":""}
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 🏦 Fundo de reserva")
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Entradas do fundo", dinheiro(k["fundo_entradas"]))
        fc2.metric("Saídas do fundo", dinheiro(k["fundo_saidas"]))
        fc3.metric("Resultado do fundo", dinheiro(k["fundo_resultado"]))

# ============================================================
# RELATÓRIO MENSAL
# ============================================================
with tabs[1]:
    st.subheader("📅 Relatório financeiro mensal")

    d = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()
    if d.empty:
        st.warning("Não há datas válidas.")
    else:
        d["Ano_Mes"] = d["Data_Analise"].dt.to_period("M").astype(str)
        linhas = []
        for mes, g in d.groupby("Ano_Mes", sort=True):
            r = resumo_financeiro(g)
            linhas.append({
                "Mês": mes,
                "Entradas": r["entradas"],
                "Saídas": r["saidas"],
                "Resultado": r["resultado"],
                "Fundo - Entradas": r["fundo_entradas"],
                "Fundo - Saídas": r["fundo_saidas"],
                "Fundo - Resultado": r["fundo_resultado"],
                "Lançamentos": len(g)
            })
        mensal = pd.DataFrame(linhas)

        st.dataframe(
            mensal.style.format({
                "Entradas": dinheiro, "Saídas": dinheiro, "Resultado": dinheiro,
                "Fundo - Entradas": dinheiro, "Fundo - Saídas": dinheiro,
                "Fundo - Resultado": dinheiro
            }),
            use_container_width=True, hide_index=True
        )

        st.info("💡 O fundo de reserva agora aparece em colunas próprias e não é misturado com o resultado geral.")

# ============================================================
# PDF
# ============================================================
with tabs[2]:
    st.subheader("📄 Relatório mensal em PDF")

    d_pdf = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()
    if d_pdf.empty:
        st.warning("Não há lançamentos com datas válidas.")
    else:
        d_pdf["Ano_Mes"] = d_pdf["Data_Analise"].dt.to_period("M").astype(str)
        meses_pdf = sorted(d_pdf["Ano_Mes"].unique(), reverse=True)
        mes = st.selectbox("Selecione o mês", meses_pdf)
        df_mes = d_pdf[d_pdf["Ano_Mes"] == mes].copy()
        r = resumo_financeiro(df_mes)

        p1,p2,p3,p4 = st.columns(4)
        p1.metric("Entradas", dinheiro(r["entradas"]))
        p2.metric("Saídas", dinheiro(r["saidas"]))
        p3.metric("Resultado", dinheiro(r["resultado"]))
        p4.metric("Fundo", dinheiro(r["fundo_resultado"]))

        pdf = gerar_pdf_mensal(df_mes, mes)
        st.download_button(
            "⬇️ Baixar PDF mensal",
            data=pdf,
            file_name=f"Relatorio_Mensal_San_Remo_{mes}.pdf",
            mime="application/pdf"
        )

# ============================================================
# FUNCIONÁRIOS
# ============================================================
with tabs[3]:
    st.subheader("👷 Funcionários")
    f = df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)]
    st.metric("Total funcionários", dinheiro(f["Valor_Absoluto"].sum()))
    st.dataframe(f, use_container_width=True, hide_index=True)

# ============================================================
# CONSUMO
# ============================================================
with tabs[4]:
    st.subheader("💡 Contas de consumo")
    f = df_filtrado[df_filtrado["Categoria"].str.startswith("Consumo", na=False)]
    resumo = f.groupby("Categoria")["Valor_Absoluto"].sum().reset_index().sort_values("Valor_Absoluto", ascending=False)
    st.dataframe(resumo.style.format({"Valor_Absoluto": dinheiro}), use_container_width=True, hide_index=True)
    st.dataframe(f, use_container_width=True, hide_index=True)

# ============================================================
# MANUTENÇÃO
# ============================================================
with tabs[5]:
    st.subheader("🛠️ Manutenção")
    f = df_filtrado[
        df_filtrado["Categoria"].str.contains("Manutenção|Elevadores|Segurança Eletrônica|Obras/Reformas|Jardinagem|Piscina|Antenas", case=False, na=False)
    ]
    resumo = f.groupby("Categoria")["Valor_Absoluto"].sum().reset_index().sort_values("Valor_Absoluto", ascending=False)
    st.dataframe(resumo.style.format({"Valor_Absoluto": dinheiro}), use_container_width=True, hide_index=True)
    st.dataframe(f, use_container_width=True, hide_index=True)

# ============================================================
# DESPESAS
# ============================================================
with tabs[6]:
    st.subheader("💸 Análise de despesas")
    s = df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"]
    ranking = s.groupby("Categoria").agg(
        Total=("Valor_Absoluto","sum"),
        Quantidade=("Valor_Absoluto","size")
    ).reset_index().sort_values("Total", ascending=False)
    st.dataframe(ranking.style.format({"Total": dinheiro}), use_container_width=True, hide_index=True)

# ============================================================
# FUNDO
# ============================================================
with tabs[7]:
    st.subheader("🏦 Fundo de reserva — controle separado")
    f = df_filtrado[df_filtrado["Categoria"] == "Fundo de reserva do condominio"].copy()

    a,b,c = st.columns(3)
    a.metric("Entradas", dinheiro(f.loc[f["Tipo_Calculado"]=="Entrada","Valor_Absoluto"].sum()))
    b.metric("Saídas", dinheiro(f.loc[f["Tipo_Calculado"]=="Saída","Valor_Absoluto"].sum()))
    c.metric("Resultado", dinheiro(
        f.loc[f["Tipo_Calculado"]=="Entrada","Valor_Absoluto"].sum()
        - f.loc[f["Tipo_Calculado"]=="Saída","Valor_Absoluto"].sum()
    ))

    if f.empty:
        st.info("Nenhuma movimentação de fundo de reserva encontrada.")
    else:
        st.dataframe(f.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

# ============================================================
# PESQUISA
# ============================================================
with tabs[8]:
    st.subheader("🔎 Pesquisa detalhada")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

# ============================================================
# CLASSIFICAÇÃO
# ============================================================
with tabs[9]:
    st.subheader("🧠 Classificação automática")
    st.dataframe(
        df[["Categoria"]].drop_duplicates().sort_values("Categoria"),
        use_container_width=True, hide_index=True
    )
    st.caption("As regras continuam baseadas no lançamento, razão social e CNPJ.")

# ============================================================
# DADOS
# ============================================================
with tabs[10]:
    st.subheader("📋 Dados completos")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
    csv_data = df_filtrado.to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button(
        "⬇️ Baixar CSV filtrado",
        data=csv_data,
        file_name="relatorio_condominio.csv",
        mime="text/csv"
    )

st.markdown("---")
st.caption("San Remo • Gestão Financeira Condominial | Dados atualizados automaticamente via Google Drive.")
