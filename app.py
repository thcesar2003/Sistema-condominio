import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import re
import unicodedata
from datetime import datetime

# Dependências do ReportLab para exportar em PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ============================================================
# CONFIGURAÇÃO DA PÁGINA E CABEÇALHO COM LOGO
# ============================================================
st.set_page_config(
    page_title="San Remo • Gestão Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

col_logo, col_titulo = st.columns([1, 5])

with col_logo:
    try:
        st.image("logo.jpg", width=110)
    except Exception:
        st.write("🏢")

with col_titulo:
    st.title("Condomínio Jardim San Remo")
    st.caption("Painel completo para análise de extratos, despesas, receitas, funcionários e relatórios mensais em PDF.")

# ============================================================
# FUNÇÕES AUXILIARES DE FORMATAÇÃO E PROCESSAMENTO
# ============================================================
def normalizar_texto(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto

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
# CLASSIFICAÇÃO AUTOMÁTICA
# ============================================================
REGRAS = {
    "Consumo - Água": ["sabesp", "saae", "agua", "saneamento", "esgoto"],
    "Consumo - Energia": ["enel", "edp", "elektro", "energia eletrica", "energia"],
    "Consumo - Gás": ["comgas", "gas natural", "gas encanado", "gas"],
    "Consumo - Telefone/Internet": ["vivo", "claro", "tim", "oi ", "telefonia", "internet", "fibra", "telefon"],
    "Salários": ["salario", "salários", "folha", "pagamento funcionario", "pagamento de funcionario", "pro labore", "pro-labore"],
    "Funcionários - Encargos": ["fgts", "inss", "gps", "e-social", "esocial", "irrf", "contribuicao previdenciaria"],
    "Funcionários - Benefícios": ["vale transporte", "vt ", "vale refeicao", "vale alimentacao", "alelo", "ticket", "cesta basica", "beneficio"],
    "Funcionários - Férias/13º": ["ferias", "férias", "decimo terceiro", "13 salario", "13º", "abono"],
    "Funcionários - Rescisões": ["rescisao", "rescisão", "multa fgts", "aviso previo", "aviso prévio"],
    "Terceirização - Portaria/Segurança": ["portaria", "seguranca", "segurança", "vigilancia", "vigia", "controlador de acesso"],
    "Terceirização - Limpeza": ["limpeza terceirizada", "conservacao", "conservação", "asseio", "limpeza"],
    "Administradora": ["administradora", "assessoria condominial", "gestao condominial", "gestão condominial"],
    "Garantidora": ["garantidora", "garantia de recebiveis", "garantia de recebíveis"],
    "Elevadores": ["elevador", "elevadores", "qualita", "manutencao elevador"],
    "Manutenção": ["manutencao", "manutenção", "conserto", "reparo", "assistencia tecnica", "assistência técnica"],
    "Limpeza/Material": ["material de limpeza", "produto de limpeza", "detergente", "desinfetante", "saco de lixo"],
    "Jardinagem": ["jardinagem", "jardim", "paisagismo", "poda"],
    "Piscina": ["piscina", "cloro", "tratamento piscina"],
    "Segurança Eletrônica": ["intelbras", "cftv", "camera", "câmera", "alarme", "monitoramento"],
    "Elevadores/Equipamentos": ["bomba", "motor", "gerador", "equipamento"],
    "Obras/Reformas": ["obra", "reforma", "pintura", "impermeabilizacao", "impermeabilização", "construcao"],
    "Seguros": ["seguro", "apolice", "apólice"],
    "Impostos/Taxas": ["tributo", "imposto", "taxa", "iss", "darf", "prefeitura"],
    "Bancárias": ["tarifa bancaria", "tarifa bancária", "tarifa", "banco", "ted", "pix tarifa"],
    "Jurídico": ["advogado", "advocacia", "juridico", "jurídico", "processo"],
    "Contabilidade": ["contabilidade", "contador", "contabil"],
}

def classificar_linha(row, colunas_texto):
    texto = " ".join(
        normalizar_texto(row.get(c, ""))
        for c in colunas_texto
        if c in row.index
    )
    for categoria, palavras in REGRAS.items():
        for palavra in palavras:
            if normalizar_texto(palavra) in texto:
                return categoria
    return "Outras Despesas" if row.get("Tipo_Calculado") == "Saída" else "Receitas"

# ============================================================
# GERADOR DE PDF (REPORTLAB)
# ============================================================
def gerar_pdf_mensal(df_mes, mes_nome, kpis_mes):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle(
        'Titulo',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=6
    )
    subtitulo_style = ParagraphStyle(
        'SubTitulo',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#4B5563'),
        spaceAfter=15
    )

    story.append(Paragraph("🏢 San Remo • Relatório Financeiro Mensal", titulo_style))
    story.append(Paragraph(f"<b>Mês de Referência:</b> {mes_nome} | <b>Emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitulo_style))
    story.append(Spacer(1, 10))

    dados_kpi = [
        ["Total Entradas", "Total Despesas", "Resultado do Mês"],
        [dinheiro(kpis_mes['entradas']), dinheiro(kpis_mes['saidas']), dinheiro(kpis_mes['resultado'])]
    ]
    tabela_kpi = Table(dados_kpi, colWidths=[180, 180, 180])
    tabela_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F3F4F6')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#1F2937')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
    ]))
    story.append(tabela_kpi)
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Resumo de Despesas por Categoria</b>", styles['Heading2']))
    cat_summary = (
        df_mes[df_mes["Tipo_Calculado"] == "Saída"]
        .groupby("Categoria")["Valor_Absoluto"]
        .sum()
        .reset_index()
        .sort_values("Valor_Absoluto", ascending=False)
    )

    dados_cat = [["Categoria", "Valor Total (R$)"]]
    for _, r in cat_summary.iterrows():
        dados_cat.append([str(r["Categoria"]), dinheiro(r["Valor_Absoluto"])])

    tabela_cat = Table(dados_cat, colWidths=[360, 180])
    tabela_cat.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))
    story.append(tabela_cat)

    doc.build(story)
    buffer.seek(0)
    return buffer
# ============================================================
# LEITURA DIRETA E TRATAMENTO AUTOMÁTICO DO GOOGLE DRIVE
# ============================================================
url = "https://drive.google.com/uc?export=download&id=1BTYPtjBHLLvSXHH_IfKrnqqwVQZ4hh4T"

@st.cache_data(ttl=300)
def carregar_dados():
    # Lê as primeiras linhas para identificar onde estão os nomes das colunas
    df_raw = pd.read_excel(url, header=None)
    
    linha_cabecalho = 0
    for idx, row in df_raw.iterrows():
        linha_texto = " ".join([normalizar_texto(val) for val in row.values if pd.notna(val)])
        if "valor" in linha_texto or "data" in linha_texto or "lancamento" in linha_texto:
            linha_cabecalho = idx
            break
            
    # Recarrega o Excel a partir da linha correta encontrada
    df_final = pd.read_excel(url, header=linha_cabecalho)
    return df_final

try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Não foi possível ler o arquivo do Google Drive: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

# ============================================================
# IDENTIFICAÇÃO E TRATAMENTO DAS COLUNAS
# ============================================================
col_valor = encontrar_coluna(df, ["valor", "valor r$", "valor (r$)", "amount"])
col_data = encontrar_coluna(df, ["data", "data lançamento", "data lancamento", "date"])

if not col_valor:
    st.error("❌ Não encontrei a coluna de valor. Renomeie a coluna para 'Valor' e tente novamente.")
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

colunas_texto = [
    c for c in [
        encontrar_coluna(df, ["lançamento", "lancamento", "histórico", "historico"]),
        encontrar_coluna(df, ["razão social", "razao social", "fornecedor", "favorecido"]),
        encontrar_coluna(df, ["cpf/cnpj", "cpf", "cnpj", "documento"]),
        encontrar_coluna(df, ["descrição", "descricao", "histórico", "historico"]),
        encontrar_coluna(df, ["complemento"]),
    ] if c
]
colunas_texto = list(dict.fromkeys(colunas_texto))

df["Categoria_Automatica"] = df.apply(
    lambda row: classificar_linha(row, colunas_texto),
    axis=1
)
df["Categoria"] = df["Categoria_Automatica"]
df["Mes"] = df["Data_Analise"].dt.to_period("M").astype(str)
df.loc[df["Mes"] == "NaT", "Mes"] = "Sem data"

# ============================================================
# FILTROS DA BARRA LATERAL
# ============================================================
st.sidebar.header("🔍 Filtros avançados")

if st.sidebar.button("🔄 Atualizar Dados do Drive"):
    st.cache_data.clear()

tipo = st.sidebar.selectbox("Tipo de lançamento", ["Todos", "Entrada", "Saída"])
categorias_sel = st.sidebar.multiselect("Categoria", sorted(df["Categoria"].dropna().unique().tolist()))
meses_sel = st.sidebar.multiselect("Mês", sorted(df["Mes"].dropna().unique().tolist()))
busca = st.sidebar.text_input("🔎 Pesquisa geral", placeholder="Fornecedor, CNPJ, descrição...")

valor_max = float(df["Valor_Absoluto"].max()) if len(df) else 0.0
faixa = st.sidebar.slider("Faixa de valor (R$)", min_value=0.0, max_value=max(valor_max, 1.0), value=(0.0, max(valor_max, 1.0)))

somente_func = st.sidebar.checkbox("👷 Somente despesas de funcionários")
somente_consumo = st.sidebar.checkbox("💡 Somente contas de consumo")

# Aplicação dos Filtros
df_filtrado = df.copy()
if tipo != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Tipo_Calculado"] == tipo]
if categorias_sel:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(categorias_sel)]
if meses_sel:
    df_filtrado = df_filtrado[df_filtrado["Mes"].isin(meses_sel)]
if busca:
    mascara = pd.Series(False, index=df_filtrado.index)
    for c in list(dict.fromkeys(colunas_texto + ["Categoria"])):
        if c in df_filtrado.columns:
            mascara |= df_filtrado[c].astype(str).str.contains(busca, case=False, na=False, regex=False)
    df_filtrado = df_filtrado[mascara]

df_filtrado = df_filtrado[(df_filtrado["Valor_Absoluto"] >= faixa[0]) & (df_filtrado["Valor_Absoluto"] <= faixa[1])]

if somente_func:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)]
if somente_consumo:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].str.startswith("Consumo", na=False)]

# ============================================================
# KPIS NO TOPO
# ============================================================
total_entradas = df_filtrado.loc[df_filtrado["Tipo_Calculado"] == "Entrada", col_valor].sum()
total_saidas = df_filtrado.loc[df_filtrado["Tipo_Calculado"] == "Saída", col_valor].abs().sum()
saldo = total_entradas - total_saidas

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Entradas", dinheiro(total_entradas))
c2.metric("💸 Despesas", dinheiro(total_saidas))
c3.metric("📈 Resultado", dinheiro(saldo))
c4.metric("📋 Lançamentos", f"{len(df_filtrado):,}".replace(",", "."))
c5.metric("👷 Funcionários", dinheiro(df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)]["Valor_Absoluto"].sum()))

# ============================================================
# ESTRUTURA DE ABAS
# ============================================================
tab_dashboard, tab_mensal, tab_pdf, tab_func, tab_consumo, tab_despesas, tab_pesquisa, tab_class, tab_dados = st.tabs([
    "📊 Dashboard",
    "📅 Relatório Mensal",
    "📄 PDF Mensal",
    "👷 Funcionários",
    "💡 Consumo",
    "💸 Despesas",
    "🔎 Pesquisa",
    "🧠 Classificação",
    "📋 Dados"
])

# 📊 DASHBOARD
with tab_dashboard:
    st.subheader("Visão geral")
    if df_filtrado.empty:
        st.warning("Nenhum lançamento corresponde aos filtros.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            resumo_tipo = df_filtrado.groupby("Tipo_Calculado")["Valor_Absoluto"].sum().reset_index()
            fig = px.pie(resumo_tipo, names="Tipo_Calculado", values="Valor_Absoluto", hole=0.45, title="Entradas x Saídas")
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            saidas_cat = df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"].groupby("Categoria")["Valor_Absoluto"].sum().reset_index().sort_values("Valor_Absoluto", ascending=False).head(12)
            fig = px.bar(saidas_cat, x="Valor_Absoluto", y="Categoria", orientation="h", title="Principais categorias de despesas")
            st.plotly_chart(fig, use_container_width=True)

# 📅 RELATÓRIO MENSAL
with tab_mensal:
    st.subheader("📅 Relatório financeiro por mês")
    d = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()
    if d.empty:
        st.warning("Não há datas válidas para gerar o relatório mensal.")
    else:
        d["Ano_Mes"] = d["Data_Analise"].dt.to_period("M").astype(str)
        mensal = d.groupby("Ano_Mes").apply(
            lambda g: pd.Series({
                "Entradas": g.loc[g["Tipo_Calculado"] == "Entrada", col_valor].sum(),
                "Despesas": g.loc[g["Tipo_Calculado"] == "Saída", col_valor].abs().sum(),
                "Resultado": g.loc[g["Tipo_Calculado"] == "Entrada", col_valor].sum() - g.loc[g["Tipo_Calculado"] == "Saída", col_valor].abs().sum(),
                "Lançamentos": len(g)
            })
        ).reset_index()
        st.dataframe(mensal.style.format({"Entradas": dinheiro, "Despesas": dinheiro, "Resultado": dinheiro}), use_container_width=True, hide_index=True)

# 📄 EXPORTAR PDF MENSAL
with tab_pdf:
    st.subheader("📄 Exportar Relatório Mensal em PDF")
    d_pdf = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()
    if d_pdf.empty:
        st.warning("Não há lançamentos com datas válidas para gerar o PDF.")
    else:
        d_pdf["Ano_Mes"] = d_pdf["Data_Analise"].dt.to_period("M").astype(str)
        meses_disponiveis = sorted(d_pdf["Ano_Mes"].unique().tolist(), reverse=True)
        mes_selecionado = st.selectbox("Selecione o mês desejado para o PDF:", meses_disponiveis)

        df_mes = d_pdf[d_pdf["Ano_Mes"] == mes_selecionado].copy()
        ent = df_mes.loc[df_mes["Tipo_Calculado"] == "Entrada", col_valor].sum()
        sai = df_mes.loc[df_mes["Tipo_Calculado"] == "Saída", col_valor].abs().sum()
        res = ent - sai

        kpis_mes = {"entradas": ent, "saidas": sai, "resultado": res}
        st.info(f"O relatório conterá os dados de **{mes_selecionado}** com **{len(df_mes)}** lançamentos.")

        pdf_bytes = gerar_pdf_mensal(df_mes, mes_selecionado, kpis_mes)
        st.download_button(
            label="⬇️ Baixar Relatório PDF",
            data=pdf_bytes,
            file_name=f"Relatorio_Mensal_{mes_selecionado}.pdf",
            mime="application/pdf"
        )

# 👷 FUNCIONÁRIOS
with tab_func:
    st.subheader("👷 Despesas de funcionários")
    df_func = df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)].copy()
    if df_func.empty:
        st.info("Nenhum lançamento de funcionário encontrado nos filtros atuais.")
    else:
        st.dataframe(df_func, use_container_width=True, hide_index=True)

# 💡 CONSUMO
with tab_consumo:
    st.subheader("💡 Contas de consumo")
    df_cons = df_filtrado[df_filtrado["Categoria"].str.startswith("Consumo", na=False)].copy()
    if df_cons.empty:
        st.info("Nenhuma conta de consumo encontrada.")
    else:
        st.dataframe(df_cons, use_container_width=True, hide_index=True)

# 💸 DESPESAS
with tab_despesas:
    st.subheader("💸 Análise completa das despesas")
    saidas = df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"].copy()
    if not saidas.empty:
        ranking = saidas.groupby("Categoria").agg(Total=("Valor_Absoluto", "sum"), Quantidade=("Valor_Absoluto", "size")).reset_index().sort_values("Total", ascending=False)
        st.dataframe(ranking.style.format({"Total": dinheiro}), use_container_width=True, hide_index=True)

# 🔎 PESQUISA
with tab_pesquisa:
    st.subheader("🔎 Pesquisa detalhada")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

# 🧠 CLASSIFICAÇÃO
with tab_class:
    st.subheader("🧠 Classificação automática")
    st.dataframe(df[["Categoria_Automatica", "Categoria"]].drop_duplicates(), use_container_width=True, hide_index=True)

# 📋 DADOS
with tab_dados:
    st.subheader("📋 Dados completos e exportação")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

    csv_data = df_filtrado.to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button("⬇️ Baixar CSV filtrado", data=csv_data, file_name="relatorio_condominio.csv", mime="text/csv")

# ============================================================
# RODAPÉ
# ============================================================
st.markdown("---")
st.caption("San Remo • Gestão Financeira Condominial | Atualizado automaticamente via GitHub & Google Drive.")