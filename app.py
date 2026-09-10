# Let's create a complete, robust, standalone Streamlit app.py with error handling, full fallback data processing, and simple PDF generation using ReportLab.
# We will verify that it runs cleanly without external socket dependency when loading defaults.

full_app_code = '''import io
import re
import unicodedata
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# Configura página do Streamlit
st.set_page_config(
    page_title="Gestão Financeira - San Remo",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

URL_DRIVE_PADRAO = "https://drive.google.com/uc?export=download&id=1DY8-BcxRhWZYPW2rhf07sZBraZk5akTe"
NOME_FUNDO = "Fundo de reserva"
NOME_ANTENAS = "Locações de espaço - Antenas"


def norm(v):
    if pd.isna(v) or v is None:
        return ""
    return unicodedata.normalize("NFKD", str(v).strip().lower()).encode("ascii", "ignore").decode("ascii")


def money(v):
    try:
        if pd.isna(v) or v is None:
            return "R$ 0,00"
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def parse_money(s):
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    x = s.astype(str).str.strip().str.replace("R$", "", regex=False).str.replace(" ", "", regex=False)
    x = x.str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
    x = x.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(x, errors="coerce")


def find_col(df, names):
    mp = {norm(c): c for c in df.columns}
    for n in names:
        if norm(n) in mp:
            return mp[norm(n)]
    for c in df.columns:
        nc = norm(c)
        if any(norm(n) in nc for n in names):
            return c
    return None


RULES = {
    "Consumo - Água": ["sabesp", "saae", "agua", "saneamento", "esgoto"],
    "Consumo - Energia": ["enel", "edp", "elektro", "energia eletrica"],
    "Consumo - Gás": ["comgas", "gas natural", "gas encanado"],
    "Consumo - Telefone/Internet": ["vivo", "claro", "tim", "oi ", "telefon", "internet", "fibra"],
    "Salários": ["salario", "folha", "pro labore", "pro-labore"],
    "Funcionários - Encargos": ["fgts", "inss", "gps", "esocial", "e-social", "irrf"],
    "Funcionários - Benefícios": ["vale transporte", "vale refeicao", "vale alimentacao", "alelo", "ticket", "cesta basica"],
    "Funcionários - Férias/13º": ["ferias", "decimo terceiro", "13 salario", "abono"],
    "Funcionários - Rescisões": ["rescisao", "multa fgts", "aviso previo"],
    "Terceirização - Portaria/Segurança": ["portaria", "seguranca", "vigilancia", "controlador de acesso"],
    "Terceirização - Limpeza": ["limpeza terceirizada", "conservacao", "asseio"],
    "Administradora": ["administradora", "assessoria condominial"],
    "Garantidora": ["garantidora"],
    "Elevadores": ["elevador", "qualita"],
    "Manutenção": ["manutencao", "conserto", "reparo", "assistencia tecnica"],
    "Limpeza/Material": ["material de limpeza", "produto de limpeza", "detergente", "desinfetante", "saco de lixo"],
    "Jardinagem": ["jardinagem", "jardim", "paisagismo", "poda"],
    "Piscina": ["piscina", "cloro", "tratamento piscina"],
    "Segurança Eletrônica": ["intelbras", "cftv", "camera", "alarme", "monitoramento"],
    "Equipamentos": ["bomba", "motor", "gerador", "equipamento"],
    "Obras/Reformas": ["obra", "reforma", "pintura", "impermeabilizacao"],
    "Seguros": ["seguro", "apolice"],
    "Impostos/Taxas": ["tributo", "imposto", "taxa", "iss", "darf", "prefeitura"],
    "Bancárias": ["tarifa bancaria", "tarifa", "ted tarifa", "pix tarifa"],
    "Jurídico": ["advogado", "advocacia", "juridico", "processo"],
    "Contabilidade": ["contabilidade", "contador", "contabil"],
}


def classify(row, value_col, desc_col, cnpj_col, razao_col):
    value = float(row[value_col]) if pd.notna(row[value_col]) else 0
    text = " ".join(norm(row.get(c, "")) for c in [desc_col, cnpj_col, razao_col] if c)
    cnpj = re.sub(r"\\D", "", str(row.get(cnpj_col, ""))) if cnpj_col else ""

    if any(x in text for x in ["aplicacao privilege int", "privilege int", "aplicacao privilege"]):
        return NOME_FUNDO

    if any(x in text for x in ["universal telecom", "directnet", "direct net"]):
        return NOME_ANTENAS

    if "51877768000189" in cnpj:
        return "Mercadinho"

    if value > 0 and abs(value - 150) < 0.01:
        return "Salão de festas"

    for cat, words in RULES.items():
        if any(norm(w) in text for w in words):
            return cat

    return "Outras Despesas" if value < 0 else "Receitas"


def calculate_monthly_balances(df_input, initial_opening_balance=0.0):
    d = df_input[df_input["Data_Analise"].notna()].sort_values(["Data_Analise", "_ordem"]).copy()
    if d.empty:
        return pd.DataFrame()

    first_month = d["Data_Analise"].min().to_period("M")
    last_month = d["Data_Analise"].max().to_period("M")

    rows = []
    current_start_balance = float(initial_opening_balance)

    for p in pd.period_range(first_month, last_month, freq="M"):
        ini, fim = pd.Timestamp(p.start_time), pd.Timestamp(p.end_time)
        g = d[(d["Data_Analise"] >= ini) & (d["Data_Analise"] <= fim)]

        saldo_inicial_mes = current_start_balance

        ent = g.loc[g["Eh_Receita"], "Valor_Absoluto"].sum()
        desp = g.loc[g["Eh_Despesa"], "Valor_Absoluto"].sum()
        fundo = g.loc[g["Eh_Fundo"], "Valor_Absoluto"].sum()

        resultado = ent - desp
        movimento = resultado - fundo

        # Verifica se há registro de saldo no extrato do Excel no mês
        valid_extrato = g[g["Saldo_Extrato"].notna()]
        real_end_balance = None
        real_date = None

        if not valid_extrato.empty:
            z = valid_extrato.sort_values(["Data_Analise", "_ordem"]).iloc[-1]
            real_end_balance = float(z["Saldo_Extrato"])
            real_date = pd.Timestamp(z["Data_Analise"])

        calculado = saldo_inicial_mes + movimento
        
        # O saldo final oficial do mês é o saldo do extrato no último dia (se disponível)
        saldo_final_mes = real_end_balance if real_end_balance is not None else calculado
        ajuste = saldo_final_mes - calculado

        rows.append({
            "Mês": str(p),
            "Saldo inicial": float(saldo_inicial_mes),
            "Entradas": float(ent),
            "Despesas": float(desp),
            "Fundo transferido": float(fundo),
            "Resultado operacional": float(resultado),
            "Movimento conta corrente": float(movimento),
            "Saldo calculado": float(calculado),
            "Saldo do extrato": real_end_balance,
            "Ajuste de conciliação": float(ajuste),
            "Saldo final": float(saldo_final_mes),
            "Data saldo real": real_date,
            "Lançamentos": len(g),
        })

        # REGRA FUNDAMENTAL: O saldo do último dia DESTE mês é o saldo INICIAL do PRÓXIMO mês
        # (Exemplo: 31/08/2026 -> Saldo R$ 56.676,66 torna-se o Saldo Inicial de 01/09/2026)
        current_start_balance = saldo_final_mes

    return pd.DataFrame(rows)


def fund_history(d):
    x = d[d["Eh_Fundo"]].copy()
    if x.empty:
        return pd.DataFrame(columns=["Mês", "Fundo no mês", "Fundo acumulado"])
    x["Mês"] = x["Data_Analise"].dt.to_period("M").astype(str)
    out = x.groupby("Mês")["Valor_Absoluto"].sum().rename("Fundo no mês").to_frame()
    allm = pd.period_range(d["Data_Analise"].min().to_period("M"), d["Data_Analise"].max().to_period("M"), freq="M").astype(str)
    out = out.reindex(allm, fill_value=0).rename_axis("Mês").reset_index()
    out["Fundo acumulado"] = out["Fundo no mês"].cumsum()
    return out


# --- INTERFACE PRINCIPAL ---
st.title("🏢 Conjunto Residencial Jardim San Remo")
st.caption("Sistema Integrado de Gestão Financeira e Conciliação Bancária")

# Sidebar para upload ou link
st.sidebar.header("📁 Fonte dos Dados")
uploaded_file = st.sidebar.file_uploader("Enviar arquivo Excel (.xlsx / .xls)", type=["xlsx", "xls"])
url_input = st.sidebar.text_input("Ou URL direta do Google Drive", value=URL_DRIVE_PADRAO)

df_raw = None

if uploaded_file is not None:
    try:
        raw = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in raw.iterrows():
            line = " ".join(norm(v) for v in row.values if pd.notna(v))
            if any(x in line for x in ["valor", "data", "lancamento", "historico", "saldo"]):
                header_idx = i
                break
        uploaded_file.seek(0)
        df_raw = pd.read_excel(uploaded_file, header=header_idx)
        st.sidebar.success("Arquivo carregado com sucesso!")
    except Exception as e:
        st.sidebar.error(f"Erro ao ler o arquivo enviado: {e}")

if df_raw is None and url_input:
    try:
        raw = pd.read_excel(url_input, header=None)
        header_idx = 0
        for i, row in raw.iterrows():
            line = " ".join(norm(v) for v in row.values if pd.notna(v))
            if any(x in line for x in ["valor", "data", "lancamento", "historico", "saldo"]):
                header_idx = i
                break
        df_raw = pd.read_excel(url_input, header=header_idx)
    except Exception as e:
        st.warning("Não foi possível carregar a URL automaticamente. Por favor, envie o arquivo Excel na barra lateral.")

if df_raw is None:
    st.info("👆 Por favor, envie o seu arquivo Excel (.xlsx) na barra lateral à esquerda para iniciar o relatório.")
    st.stop()

# Processamento do DataFrame
df = df_raw.copy()
df.columns = [str(c).strip() for c in df.columns]

col_valor = find_col(df, ["valor", "valor r$", "amount"])
col_data = find_col(df, ["data lancamento", "data lançamento", "data", "date"])
col_desc = find_col(df, ["lancamento", "lançamento", "historico", "histórico", "descricao", "descrição", "complemento"])
col_cnpj = find_col(df, ["cpf/cnpj", "cpf", "cnpj", "documento"])
col_razao = find_col(df, ["razao social", "razão social", "fornecedor", "favorecido"])

col_saldo = find_col(df, [
    "saldo total disponivel",
    "saldo total disponível",
    "saldo disponivel do dia",
    "saldo disponível do dia",
    "saldo disponivel dia",
    "saldo disponível dia",
    "saldo conta corrente",
    "saldo da conta corrente",
    "saldo corrente",
    "saldo disponível",
    "saldo disponivel",
    "saldo final",
    "saldo",
])

if not col_valor or not col_data:
    st.error("Não foram encontradas as colunas necessárias de Data e Valor na planilha.")
    st.write("Colunas identificadas:", list(df.columns))
    st.stop()

df[col_valor] = parse_money(df[col_valor])
df["Data_Analise"] = pd.to_datetime(df[col_data], dayfirst=True, errors="coerce")
df = df.dropna(subset=[col_valor, "Data_Analise"]).copy()
df["_ordem"] = range(len(df))
df["Tipo_Calculado"] = df[col_valor].apply(lambda x: "Entrada" if x > 0 else "Saída" if x < 0 else "Neutro")
df["Valor_Absoluto"] = df[col_valor].abs()
df["Categoria"] = df.apply(lambda r: classify(r, col_valor, col_desc, col_cnpj, col_razao), axis=1)

if col_saldo:
    df["Saldo_Extrato"] = parse_money(df[col_saldo])
else:
    df["Saldo_Extrato"] = pd.Series(pd.NA, index=df.index, dtype="Float64")

df["Mes"] = df["Data_Analise"].dt.to_period("M").astype(str)
df["Eh_Fundo"] = df["Categoria"].eq(NOME_FUNDO)
df["Eh_Receita"] = (df["Tipo_Calculado"] == "Entrada") & (~df["Eh_Fundo"])
df["Eh_Despesa"] = (df["Tipo_Calculado"] == "Saída") & (~df["Eh_Fundo"])
df = df.sort_values(["Data_Analise", "_ordem"]).reset_index(drop=True)

# Parâmetros de Conciliação
st.sidebar.header("⚙️ Parâmetros")
opening_balance_input = st.sidebar.number_input("Saldo inicial anterior ao 1º mês (R$)", min_value=0.0, value=0.0, step=100.0)

saldos = calculate_monthly_balances(df, opening_balance_input)
fund = fund_history(df)

# Filtros
st.sidebar.header("🔎 Filtros de Exibição")
tipo_f = st.sidebar.selectbox("Tipo de Movimento", ["Todos", "Entrada", "Saída"])
cats_f = st.sidebar.multiselect("Categorias", sorted(df["Categoria"].unique()))
months_f = st.sidebar.multiselect("Meses", sorted(df["Mes"].unique()))
search_f = st.sidebar.text_input("Buscar texto")

f = df.copy()
if tipo_f != "Todos":
    f = f[f["Tipo_Calculado"] == tipo_f]
if cats_f:
    f = f[f["Categoria"].isin(cats_f)]
if months_f:
    f = f[f["Mes"].isin(months_f)]
if search_f:
    cols_search = [c for c in [col_desc, col_cnpj, col_razao, "Categoria"] if c]
    mask = pd.Series(False, index=f.index)
    for c in cols_search:
        mask |= f[c].astype(str).str.contains(search_f, case=False, na=False, regex=False)
    f = f[mask]

# Métricas Principais
entradas = f.loc[f["Eh_Receita"], "Valor_Absoluto"].sum()
despesas = f.loc[f["Eh_Despesa"], "Valor_Absoluto"].sum()
fundo_total = f.loc[f["Eh_Fundo"], "Valor_Absoluto"].sum()
resultado = entradas - despesas
movimento = resultado - fundo_total

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Arrecadação (+)", money(entradas))
c2.metric("Despesas (-)", money(despesas))
c3.metric("Resultado Op.", money(resultado))
c4.metric("Mov. Conta", money(movimento))
c5.metric("Saldo Final", money(saldos.iloc[-1]["Saldo final"]) if not saldos.empty else "R$ 0,00")

st.markdown("---")

# Abas de Navegação
t_dash, t_concil, t_pdf, t_dados = st.tabs([
    "📊 Dashboard",
    "📅 Conciliação Mensal",
    "📄 Gerar Relatório PDF",
    "📋 Dados Consolidados"
])

with t_dash:
    st.subheader("Visão Geral do Período")
    if not f.empty:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            g_df = f.assign(Ano_Mes=f["Data_Analise"].dt.to_period("M").astype(str)).groupby(["Ano_Mes", "Tipo_Calculado"])["Valor_Absoluto"].sum().reset_index()
            fig1 = px.bar(g_df, x="Ano_Mes", y="Valor_Absoluto", color="Tipo_Calculado", barmode="group", title="Entradas x Saídas por Mês")
            st.plotly_chart(fig1, use_container_width=True)
        with col_g2:
            fig2 = px.line(saldos, x="Mês", y="Saldo final", markers=True, title="Evolução do Saldo Final da Conta")
            st.plotly_chart(fig2, use_container_width=True)

with t_concil:
    st.subheader("Tabela de Conciliação Financeira Mensal")
    st.write("📌 **Regra Ativa:** O saldo do último dia do mês N é rigorosamente mantido como o Saldo Inicial do mês N+1 (exemplo: saldo em 31/08/2026 de R$ 56.676,66 é o Saldo Inicial de Setembro/2026).")
    
    if not saldos.empty:
        format_cols = [c for c in ["Saldo inicial", "Entradas", "Despesas", "Fundo transferido", "Resultado operacional", "Movimento conta corrente", "Saldo calculado", "Saldo do extrato", "Ajuste de conciliação", "Saldo final"] if c in saldos.columns]
        st.dataframe(
            saldos.style.format({c: money for c in format_cols}),
            use_container_width=True,
            hide_index=True
        )

with t_pdf:
    st.subheader("Emissão do Relatório Financeiro Mensal em PDF")
    if saldos.empty:
        st.warning("Nenhum dado disponível para gerar o PDF.")
    else:
        mes_sel = st.selectbox("Selecione o Mês para Download do Relatório", saldos["Mês"].tolist())
        row_s = saldos[saldos["Mês"] == mes_sel].iloc[0]
        df_mes = df[df["Mes"] == mes_sel].sort_values(["Data_Analise", "_ordem"])

        if st.button("🔨 Gerar Arquivo PDF Oficial"):
            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=landscape(A4),
                rightMargin=20,
                leftMargin=20,
                topMargin=20,
                bottomMargin=20
            )
            styles = getSampleStyleSheet()

            style_title = styles["Title"]
            style_title.fontSize = 16
            style_sub = styles["Heading2"]
            style_sub.fontSize = 12

            elements = [
                Paragraph("CONJUNTO RESIDENCIAL JARDIM SAN REMO", style_title),
                Paragraph(f"Relatório Financeiro e Conciliação Bancária - Mês: {mes_sel}", style_sub),
                Spacer(1, 15),
            ]

            # Tabela Resumo
            resumo_grid = [
                ["Saldo Inicial", "Arrecadação (+)", "Despesas (-)", "Fundo Reserva (-)", "Resultado Op.", "Saldo Final Extrato"],
                [
                    money(row_s["Saldo inicial"]),
                    money(row_s["Entradas"]),
                    money(row_s["Despesas"]),
                    money(row_s["Fundo transferido"]),
                    money(row_s["Resultado operacional"]),
                    money(row_s["Saldo final"]),
                ]
            ]
            t_res = Table(resumo_grid, colWidths=[120, 110, 110, 110, 110, 130])
            t_res.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F2F2F2")),
            ]))
            elements.append(t_res)
            elements.append(Spacer(1, 15))

            # Resumo de Categoria
            cat_df = df_mes.groupby(["Tipo_Calculado", "Categoria"])["Valor_Absoluto"].sum().reset_index()
            cat_rows = [["Tipo", "Categoria", "Total do Mês"]]
            for r_c in cat_df.itertuples():
                cat_rows.append([str(r_c.Tipo_Calculado), str(r_c.Categoria), money(r_c.Valor_Absoluto)])

            t_cat = Table(cat_rows, colWidths=[120, 420, 150])
            t_cat.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            elements.append(Paragraph("Resumo de Gastos e Receitas por Categoria", style_sub))
            elements.append(Spacer(1, 5))
            elements.append(t_cat)

            doc.build(elements)
            buf.seek(0)

            st.download_button(
                label=f"⬇️ Baixar PDF ({mes_sel})",
                data=buf.getvalue(),
                file_name=f"Relatorio_San_Remo_{mes_sel}.pdf",
                mime="application/pdf"
            )

with t_dados:
    st.subheader("Base de Lançamentos Filtrada")
    st.dataframe(f.sort_values("Data_Analise"), use_container_width=True, hide_index=True)
'''

with open("app.py", "w", encoding="utf-8") as f:
    f.write(full_app_code)

print("Novo app.py gravado com sucesso! Tamanho:", len(full_app_code))