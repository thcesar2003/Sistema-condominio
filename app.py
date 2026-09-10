import io
import re
import unicodedata
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

st.set_page_config(page_title="San Remo - Gestão Financeira", page_icon="🏢", layout="wide")

URL_DRIVE = "https://drive.google.com/uc?export=download&id=1DY8-BcxRhWZYPW2rhf07sZBraZk5akTe"
NOME_FUNDO = "Fundo de reserva"
NOME_ANTENAS = "Locações de espaço - Antenas"


def norm(v):
    if pd.isna(v):
        return ""
    return unicodedata.normalize("NFKD", str(v).strip().lower()).encode("ascii", "ignore").decode("ascii")


def money(v):
    try:
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
    cnpj = re.sub(r"\D", "", str(row.get(cnpj_col, ""))) if cnpj_col else ""

    if any(x in text for x in ["aplicacao privilege int", "privilege int", "aplicacao privilege"]):
        return NOME_FUNDO

    # IMPORTANT: these are incoming antenna-space rents.
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


@st.cache_data(ttl=300)
def load_excel():
    raw = pd.read_excel(URL_DRIVE, header=None)
    header = 0
    for i, row in raw.iterrows():
        line = " ".join(norm(v) for v in row.values if pd.notna(v))
        if any(x in line for x in ["valor", "data", "lancamento", "historico", "saldo"]):
            header = i
            break
    return pd.read_excel(URL_DRIVE, header=header)


def monthly_balances(d, opening_balance):
    d = d[d["Data_Analise"].notna()].sort_values(["Data_Analise", "_ordem"]).copy()
    if d.empty:
        return pd.DataFrame()

    first = d["Data_Analise"].min().to_period("M")
    last = d["Data_Analise"].max().to_period("M")

    # Search for a real balance before January; otherwise use configured opening.
    prior = d[d["Data_Analise"] < pd.Timestamp(first.start_time)]
    saldo = None
    if not prior.empty:
        valid = prior[prior["Saldo_Extrato"].notna()]
        if not valid.empty:
            saldo = float(valid.sort_values(["Data_Analise", "_ordem"]).iloc[-1]["Saldo_Extrato"])

    saldo = float(opening_balance) if saldo is None else saldo
    rows = []

    for p in pd.period_range(first, last, freq="M"):
        ini, fim = pd.Timestamp(p.start_time), pd.Timestamp(p.end_time)
        g = d[(d["Data_Analise"] >= ini) & (d["Data_Analise"] <= fim)]

        ent = g.loc[g["Eh_Receita"], "Valor_Absoluto"].sum()
        desp = g.loc[g["Eh_Despesa"], "Valor_Absoluto"].sum()
        fundo = g.loc[g["Eh_Fundo"], "Valor_Absoluto"].sum()

        resultado = ent - desp
        movimento = resultado - fundo
        calculado = saldo + movimento

        real = None
        real_date = None
        valid = g[g["Saldo_Extrato"].notna()]
        if not valid.empty:
            z = valid.sort_values(["Data_Analise", "_ordem"]).iloc[-1]
            real = float(z["Saldo_Extrato"])
            real_date = pd.Timestamp(z["Data_Analise"])

        final = calculado if real is None else real
        ajuste = 0 if real is None else real - calculado

        rows.append({
            "Mês": str(p),
            "Saldo inicial": float(saldo),
            "Entradas": float(ent),
            "Despesas": float(desp),
            "Fundo transferido": float(fundo),
            "Resultado operacional": float(resultado),
            "Movimento conta corrente": float(movimento),
            "Saldo calculado": float(calculado),
            "Saldo do extrato": real,
            "Ajuste de conciliação": float(ajuste),
            "Saldo final": float(final),
            "Data saldo real": real_date,
            "Lançamentos": len(g),
        })

        # THE KEY RULE: month closing balance becomes next month's opening balance.
        saldo = final

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


# ---------------- LOAD / PREPARE ----------------
if st.sidebar.button("🔄 Atualizar dados do Drive"):
    st.cache_data.clear()
    st.rerun()

try:
    df = load_excel()
except Exception as e:
    st.error("Erro ao carregar o Excel do Google Drive.")
    st.exception(e)
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

col_valor = find_col(df, ["valor", "valor r$", "amount"])
col_data = find_col(df, ["data lancamento", "data lançamento", "data", "date"])
col_desc = find_col(df, ["lancamento", "lançamento", "historico", "histórico", "descricao", "descrição", "complemento"])
col_cnpj = find_col(df, ["cpf/cnpj", "cpf", "cnpj", "documento"])
col_razao = find_col(df, ["razao social", "razão social", "fornecedor", "favorecido"])

# Prefer the current-account balance explicitly. Do not confuse it with investment balance.
col_saldo = find_col(df, [
    "saldo conta corrente",
    "saldo da conta corrente",
    "saldo conta-corrente",
    "saldo corrente",
    "saldo disponível conta corrente",
    "saldo disponivel conta corrente",
    "saldo disponível",
    "saldo disponivel",
    "saldo atual",
    "saldo final",
    "saldo",
    "balance",
])

if not col_valor or not col_data:
    st.error("O Excel precisa ter colunas de Data e Valor.")
    st.write("Colunas encontradas:", list(df.columns))
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

st.sidebar.header("🏦 Conciliação")
opening = st.sidebar.number_input("Saldo inicial anterior ao primeiro mês", min_value=0.0, value=0.0, step=100.0)

saldos = monthly_balances(df, opening)
fund = fund_history(df)

st.sidebar.header("🔎 Filtros")
tipo = st.sidebar.selectbox("Tipo", ["Todos", "Entrada", "Saída"])
cats = st.sidebar.multiselect("Categoria", sorted(df["Categoria"].unique()))
months = st.sidebar.multiselect("Mês", sorted(df["Mes"].unique()))
search = st.sidebar.text_input("Pesquisa")
mx = max(float(df["Valor_Absoluto"].max()), 1)
rng = st.sidebar.slider("Faixa de valor", 0.0, mx, (0.0, mx))

f = df.copy()
if tipo != "Todos":
    f = f[f["Tipo_Calculado"] == tipo]
if cats:
    f = f[f["Categoria"].isin(cats)]
if months:
    f = f[f["Mes"].isin(months)]
if search:
    cols = [c for c in [col_desc, col_cnpj, col_razao, "Categoria"] if c]
    mask = pd.Series(False, index=f.index)
    for c in cols:
        mask |= f[c].astype(str).str.contains(search, case=False, na=False, regex=False)
    f = f[mask]
f = f[(f["Valor_Absoluto"] >= rng[0]) & (f["Valor_Absoluto"] <= rng[1])]

entradas = f.loc[f["Eh_Receita"], "Valor_Absoluto"].sum()
despesas = f.loc[f["Eh_Despesa"], "Valor_Absoluto"].sum()
fundo_total = f.loc[f["Eh_Fundo"], "Valor_Absoluto"].sum()
resultado = entradas - despesas
movimento = resultado - fundo_total

st.title("🏢 Conjunto Residencial Jardim San Remo")
st.caption("Gestão financeira • conta corrente • fundo de reserva • conciliação bancária")

a,b,c,d,e = st.columns(5)
a.metric("Arrecadação", money(entradas))
b.metric("Despesas", money(despesas))
c.metric("Resultado operacional", money(resultado))
d.metric("Movimento da conta", money(movimento))
e.metric("Saldo final", money(saldos.iloc[-1]["Saldo final"]) if not saldos.empty else "R$ 0,00")

tabs = st.tabs(["📊 Dashboard","📅 Relatório mensal","🏦 Saldo da conta","💰 Fundo","💵 Arrecadação","👷 Funcionários","💡 Consumo","🛠️ Manutenção","💸 Despesas","🔎 Pesquisa","📄 PDF","📋 Dados"])

with tabs[0]:
    st.subheader("Dashboard")
    if not f.empty:
        x = f.assign(Ano_Mes=f["Data_Analise"].dt.to_period("M").astype(str)).groupby(["Ano_Mes","Tipo_Calculado"])["Valor_Absoluto"].sum().reset_index()
        st.plotly_chart(px.bar(x, x="Ano_Mes", y="Valor_Absoluto", color="Tipo_Calculado", barmode="group", title="Entradas x Saídas por mês"), use_container_width=True)
        st.plotly_chart(px.line(saldos, x="Mês", y="Saldo final", markers=True, title="Saldo final da conta corrente"), use_container_width=True)

with tabs[1]:
    st.subheader("Relatório mensal")
    if saldos.empty:
        st.warning("Sem histórico.")
    else:
        st.dataframe(saldos.style.format({c: money for c in ["Saldo inicial","Entradas","Despesas","Fundo transferido","Resultado operacional","Movimento conta corrente","Saldo calculado","Saldo do extrato","Ajuste de conciliação","Saldo final"]}), use_container_width=True, hide_index=True)
        st.info("Regra fixa: saldo final de cada mês = saldo inicial do mês seguinte. O saldo do extrato é usado quando disponível.")

with tabs[2]:
    st.subheader("Conciliação da conta corrente")
    if col_saldo:
        st.success(f"Saldo bancário identificado na coluna: {col_saldo}")
    else:
        st.warning("Não foi identificada coluna de saldo no Excel; o sistema mostra apenas o saldo calculado.")
    st.dataframe(saldos.style.format({c: money for c in ["Saldo inicial","Entradas","Despesas","Fundo transferido","Resultado operacional","Movimento conta corrente","Saldo calculado","Saldo do extrato","Ajuste de conciliação","Saldo final"]}), use_container_width=True, hide_index=True)
    st.markdown("### Regra do encadeamento")
    st.write("31/08/2026 → saldo final de agosto → saldo inicial de setembro → lançamentos de setembro → saldo de 09/09/2026.")
    if not saldos.empty:
        z=saldos.iloc[-1]
        st.metric("Último saldo bancário reconhecido", money(z["Saldo final"]))
        st.caption(f"Data do saldo: {z['Data saldo real'].strftime('%d/%m/%Y') if pd.notna(z['Data saldo real']) else 'não disponível'}")
        st.metric("Ajuste de conciliação", money(z["Ajuste de conciliação"]))

with tabs[3]:
    st.subheader("Fundo de reserva")
    st.dataframe(fund.style.format({"Fundo no mês":money,"Fundo acumulado":money}), use_container_width=True, hide_index=True)
    if not fund.empty:
        st.metric("Fundo acumulado", money(fund.iloc[-1]["Fundo acumulado"]))
    st.info("Fundo positivo e acumulativo. Não é despesa operacional, mas reduz o caixa da conta corrente.")

with tabs[4]:
    st.subheader("Arrecadação")
    r=f[f["Eh_Receita"]]
    st.metric("Total", money(r["Valor_Absoluto"].sum()))
    st.dataframe(r.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("Funcionários")
    r=f[f["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)]
    st.metric("Total", money(r["Valor_Absoluto"].sum()))
    st.dataframe(r.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

with tabs[6]:
    st.subheader("Consumo")
    r=f[f["Categoria"].str.startswith("Consumo", na=False)]
    st.dataframe(r.groupby("Categoria")["Valor_Absoluto"].sum().reset_index().sort_values("Valor_Absoluto", ascending=False).style.format({"Valor_Absoluto":money}), use_container_width=True, hide_index=True)
    st.dataframe(r.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

with tabs[7]:
    st.subheader("Manutenção")
    cats_m=["Manutenção","Elevadores","Segurança Eletrônica","Equipamentos","Obras/Reformas","Jardinagem","Piscina"]
    r=f[f["Categoria"].isin(cats_m)]
    st.dataframe(r.sort_values("Data_Analise"), use_container_width=True, hide_index=True)
    st.info("Universal Telecom e Directnet são receitas de locação de espaço para antenas.")

with tabs[8]:
    st.subheader("Despesas")
    r=f[f["Eh_Despesa"]]
    st.dataframe(r.groupby("Categoria")["Valor_Absoluto"].sum().reset_index().sort_values("Valor_Absoluto", ascending=False).style.format({"Valor_Absoluto":money}), use_container_width=True, hide_index=True)
    st.dataframe(r.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

with tabs[9]:
    st.subheader("Pesquisa detalhada")
    st.dataframe(f.sort_values("Data_Analise"), use_container_width=True, hide_index=True)

with tabs[10]:
    st.subheader("PDF mensal")
    if not saldos.empty:
        opt=st.selectbox("Mês", saldos["Mês"].tolist())
        row=saldos[saldos["Mês"]==opt].iloc[0]
        dm=df[df["Mes"]==opt]
        buf=io.BytesIO()
        doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=25,leftMargin=25,topMargin=25,bottomMargin=25)
        styles=getSampleStyleSheet()
        story=[Paragraph("CONJUNTO RESIDENCIAL JARDIM SAN REMO",styles["Title"]),Paragraph(f"Relatório Financeiro - {opt}",styles["Heading2"]),Spacer(1,10)]
        data=[["Saldo inicial","Arrecadação","Despesas","Fundo","Resultado","Saldo final"],[money(row["Saldo inicial"]),money(row["Entradas"]),money(row["Despesas"]),money(row["Fundo transferido"]),money(row["Resultado operacional"]),money(row["Saldo final"])]]
        t=Table(data,repeatRows=1); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),.5,colors.grey),("ALIGN",(0,0),(-1,-1),"CENTER")]))
        story += [t,Spacer(1,12),Paragraph("Resumo por categoria",styles["Heading2"])]
        cat=dm.groupby(["Tipo_Calculado","Categoria"])["Valor_Absoluto"].sum().reset_index()
        rows=[["Tipo","Categoria","Valor"]]+[[str(x.Tipo_Calculado),str(x.Categoria),money(x.Valor_Absoluto)] for x in cat.itertuples()]
        t2=Table(rows,repeatRows=1); t2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),.4,colors.grey),("ALIGN",(2,1),(2,-1),"RIGHT")]))
        story += [t2,Spacer(1,10),Paragraph(f"Ajuste de conciliação: {money(row['Ajuste de conciliação'])}",styles["Normal"])]
        doc.build(story); buf.seek(0)
        st.download_button("⬇️ Baixar PDF",buf.getvalue(),f"Relatorio_San_Remo_{opt}.pdf","application/pdf")

with tabs[11]:
    st.subheader("Dados completos")
    st.dataframe(f.sort_values("Data_Analise"), use_container_width=True, hide_index=True)
    st.download_button("⬇️ Baixar CSV",f.to_csv(index=False,sep=";",encoding="utf-8-sig"),"san_remo_filtrado.csv","text/csv")

st.markdown("---")
st.caption("San Remo • saldo encadeado mês a mês • conciliação com extrato bancário")
