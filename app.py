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
# CORREÇÃO DEFINITIVA DE SALDO / RELATÓRIO / PDF
#
# Regra financeira:
#   saldo final real do mês = saldo inicial do mês seguinte
#
# O extrato possui linhas de saldo que aparecem, em alguns dias,
# antes dos lançamentos daquele mesmo dia. Por isso o sistema:
#   1) separa lançamentos de linhas de saldo;
#   2) soma somente os lançamentos no movimento;
#   3) identifica o saldo diário pela DATA, não pela posição da linha;
#   4) prioriza "SALDO EM CONTA CORRENTE";
#   5) usa "SALDO TOTAL DISPONÍVEL DIA" quando não houver saldo
#      explícito de conta corrente naquele dia;
#   6) usa o último saldo real do mês como fechamento;
#   7) carrega esse fechamento para a abertura do mês seguinte.
#
# Conferência confirmada no extrato enviado:
# 30/04/2026: saldo = R$ 40.451,52
# 05/05/2026:
#   - R$ 1.456,21
#   - R$    15,02
#   + R$13.000,00
#   = R$11.528,77 de movimento
# 40.451,52 + 11.528,77 = R$51.980,29
#
# ============================================================

st.set_page_config(
    page_title="San Remo • Gestão Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

URL_DRIVE = "https://drive.google.com/uc?export=download&id=1DY8-BcxRhWZYPW2rhf07sZBraZk5akTe"
NOME_FUNDO = "Fundo de reserva do condominio"
SALDO_INICIAL_FUNDO = 45881.72

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
    "Salários": ["salario", "folha", "pagamento funcionario", "pagamento de funcionario", "pro labore"],
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
    "Equipamentos": ["bomba", "motor", "gerador", "equipamento"],
    "Obras/Reformas": ["obra", "reforma", "pintura", "impermeabilizacao", "construcao"],
    "Seguros": ["seguro", "apolice"],
    "Impostos/Taxas": ["tributo", "imposto", "taxa", "iss", "darf", "prefeitura"],
    "Jurídico": ["advogado", "advocacia", "juridico", "processo"],
    "Contabilidade": ["contabilidade", "contador", "contabil"],
}

def classificar_linha(row, col_valor, col_lanc, col_cnpj, col_razao):
    txt_lanc = normalizar_texto(row.get(col_lanc, "")) if col_lanc else ""
    txt_cnpj = str(row.get(col_cnpj, "")).strip() if col_cnpj and pd.notna(row.get(col_cnpj)) else ""
    txt_razao = normalizar_texto(row.get(col_razao, "")) if col_razao else ""
    valor = float(row.get(col_valor, 0) or 0)
    tipo = "Entrada" if valor > 0 else ("Saída" if valor < 0 else "Neutro")
    texto = f"{txt_lanc} {txt_razao} {txt_cnpj}".strip()

    # Fundo: transferência da conta corrente para aplicação.
    if "aplicacao privilege int" in txt_lanc or "privilege int" in txt_lanc:
        return NOME_FUNDO

    # Receitas de antenas.
    if "universal telecom" in texto or "directnet" in texto or "direct net" in texto:
        return "Locações de espaço - Antenas"

    # Entrada de salão.
    if tipo == "Entrada" and abs(valor - 150.0) < 0.01:
        return "Salão de festas"

    # Mercadinho.
    if "51877768000189" in re.sub(r"\D", "", txt_cnpj) or "51877768000189" in re.sub(r"\D", "", texto):
        return "Mercadinho"

    # Importante: não classificar TED/Pix recebido como "Bancárias".
    # Tarifas/banco são despesas quando o valor é negativo.
    if tipo == "Entrada":
        return "Receitas"

    # Regras somente para saídas.
    for categoria, palavras in REGRAS.items():
        if any(normalizar_texto(p) in texto for p in palavras):
            return categoria

    return "Outras Despesas"

# ============================================================
# LEITURA DO EXTRATO
# ============================================================

@st.cache_data(ttl=300)
def carregar_dados():
    # Lê primeiro sem cabeçalho para não perder as linhas de saldo.
    raw = pd.read_excel(URL_DRIVE, header=None)

    linha_cabecalho = 0
    for idx, row in raw.iterrows():
        linha = " ".join(normalizar_texto(v) for v in row.values if pd.notna(v))
        if "valor" in linha and ("data" in linha or "lancamento" in linha):
            linha_cabecalho = idx
            break

    df = pd.read_excel(URL_DRIVE, header=linha_cabecalho)
    df.columns = [str(c).strip() for c in df.columns]
    return df

try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Não foi possível ler o arquivo do Google Drive: {e}")
    st.stop()

col_valor = encontrar_coluna(df, ["valor", "valor r$", "valor (r$)", "amount"])
col_data = encontrar_coluna(df, ["data", "data lançamento", "data lancamento", "date"])
col_lanc = encontrar_coluna(df, ["lançamento", "lancamento", "histórico", "historico"])
col_cnpj = encontrar_coluna(df, ["cpf/cnpj", "cpf", "cnpj", "documento"])
col_razao = encontrar_coluna(df, ["razão social", "razao social", "fornecedor", "favorecido"])

if not col_valor or not col_data:
    st.error("Não encontrei as colunas obrigatórias de Data e Valor.")
    st.write("Colunas encontradas:", list(df.columns))
    st.stop()

# ------------------------------------------------------------
# Identificação segura da coluna de saldo.
# Preferimos saldo da conta corrente. Se não houver, usamos
# saldo total disponível como referência bancária do extrato.
# ------------------------------------------------------------

col_saldo_cc = encontrar_coluna(df, [
    "saldo em conta corrente",
    "saldo conta corrente",
    "saldo da conta corrente",
    "saldo corrente",
    "saldo cc",
    "saldo c/c",
])

col_saldo_total = encontrar_coluna(df, [
    "saldo total disponível dia",
    "saldo total disponivel dia",
])

col_saldo_generico = encontrar_coluna(df, [
    "saldo",
    "balance",
])

df["_Valor"] = limpar_valor(df[col_valor])
df["_Data"] = pd.to_datetime(df[col_data], dayfirst=True, errors="coerce")

# Linha de saldo NÃO é lançamento.
texto_lanc = df[col_lanc].fillna("").astype(str).map(normalizar_texto) if col_lanc else pd.Series("", index=df.index)

df["_EhSaldoCC"] = texto_lanc.str.contains("saldo em conta corrente", regex=False)
df["_EhSaldoTotal"] = texto_lanc.str.contains("saldo total disponivel dia", regex=False)
df["_EhSaldoAnterior"] = texto_lanc.str.contains("saldo anterior", regex=False)

# Detecta saldo na coluna quando houver valor nela.
df["_SaldoCC"] = pd.NA
df["_SaldoTotal"] = pd.NA

if col_saldo_cc:
    df["_SaldoCC"] = limpar_valor(df[col_saldo_cc])
if col_saldo_total:
    df["_SaldoTotal"] = limpar_valor(df[col_saldo_total])

# Alguns extratos colocam "SALDO..." na coluna Lançamento e o número
# na coluna Saldo. Se só existir coluna genérica, aproveitamos.
if col_saldo_generico:
    gen = limpar_valor(df[col_saldo_generico])
    if not col_saldo_cc:
        df.loc[df["_EhSaldoCC"], "_SaldoCC"] = gen[df["_EhSaldoCC"]]
    if not col_saldo_total:
        df.loc[df["_EhSaldoTotal"], "_SaldoTotal"] = gen[df["_EhSaldoTotal"]]

# Linhas de saldo reconhecidas são retiradas dos lançamentos.
df["_EhLinhaSaldo"] = (
    df["_EhSaldoCC"] |
    df["_EhSaldoTotal"] |
    df["_EhSaldoAnterior"] |
    texto_lanc.str.contains("saldo", regex=False)
)

lanc = df[(df["_Valor"].notna()) & (~df["_EhLinhaSaldo"]) & (df["_Data"].notna())].copy()
lanc["_Ordem"] = lanc.index

lanc["Tipo"] = lanc["_Valor"].apply(lambda x: "Entrada" if x > 0 else ("Saída" if x < 0 else "Neutro"))
lanc["Valor_Absoluto"] = lanc["_Valor"].abs()
lanc["Categoria"] = lanc.apply(
    lambda row: classificar_linha(row, "_Valor", col_lanc, col_cnpj, col_razao),
    axis=1,
)
lanc["Mes"] = lanc["_Data"].dt.to_period("M").astype(str)

# ============================================================
# SALDOS DIÁRIOS REAIS
# ============================================================

saldo_rows = df[df["_Data"].notna()].copy()

# Para cada dia:
# 1. se houver saldo em conta corrente, ele vence;
# 2. senão, saldo total disponível;
# 3. se houver vários registros do mesmo tipo, usamos o último valor
#    existente na própria planilha.
def construir_saldos_diarios(base):
    rows = []
    for data, g in base.groupby("_Data"):
        g = g.sort_index()

        cc = g[g["_SaldoCC"].notna()]
        total = g[g["_SaldoTotal"].notna()]

        saldo = None
        origem = None

        if not cc.empty:
            saldo = float(cc.iloc[-1]["_SaldoCC"])
            origem = "Saldo em conta corrente"
        elif not total.empty:
            saldo = float(total.iloc[-1]["_SaldoTotal"])
            origem = "Saldo total disponível do dia"
        else:
            continue

        rows.append({
            "Data": pd.Timestamp(data),
            "Saldo Real": saldo,
            "Origem": origem,
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Data").reset_index(drop=True)
    return out

saldos_diarios = construir_saldos_diarios(saldo_rows)

# Saldo anterior ao primeiro lançamento de 2026, quando existente.
saldo_anterior = None
if not saldos_diarios.empty:
    ant = saldo_rows[
        (saldo_rows["_Data"] < pd.Timestamp("2026-01-01")) &
        (saldo_rows["_SaldoCC"].notna() | saldo_rows["_SaldoTotal"].notna())
    ]
    if not ant.empty:
        cc = ant[ant["_SaldoCC"].notna()]
        if not cc.empty:
            saldo_anterior = float(cc.sort_index().iloc[-1]["_SaldoCC"])
        else:
            total = ant[ant["_SaldoTotal"].notna()]
            if not total.empty:
                saldo_anterior = float(total.sort_index().iloc[-1]["_SaldoTotal"])

if saldo_anterior is None:
    # Fallback somente se o extrato não trouxer saldo anterior.
    saldo_anterior = 0.0

# ============================================================
# CRONOGRAMA MENSAL
# ============================================================

def resumo_periodo(g):
    entradas = g[(g["Tipo"] == "Entrada") & (g["Categoria"] != NOME_FUNDO)]["Valor_Absoluto"].sum()
    despesas = g[(g["Tipo"] == "Saída") & (g["Categoria"] != NOME_FUNDO)]["Valor_Absoluto"].sum()

    fundo_saida = g[(g["Categoria"] == NOME_FUNDO) & (g["Tipo"] == "Saída")]["Valor_Absoluto"].sum()
    fundo_entrada = g[(g["Categoria"] == NOME_FUNDO) & (g["Tipo"] == "Entrada")]["Valor_Absoluto"].sum()

    return {
        "entradas": float(entradas),
        "despesas": float(despesas),
        "resultado": float(entradas - despesas),
        "fundo_saida": float(fundo_saida),
        "fundo_entrada": float(fundo_entrada),
        "fundo_liquido": float(fundo_saida - fundo_entrada),
    }

def cronograma_mensal(d, saldo_abertura, fundo_abertura):
    if d.empty:
        return pd.DataFrame()

    meses = sorted(d["Mes"].dropna().unique())
    saldo = float(saldo_abertura)
    fundo = float(fundo_abertura)
    linhas = []

    for mes in meses:
        g = d[d["Mes"] == mes].sort_values(["_Data", "_Ordem"])
        r = resumo_periodo(g)

        movimento = r["resultado"] - r["fundo_liquido"]
        saldo_calculado = saldo + movimento

        # Fechamento REAL:
        # escolhemos o último dia do mês que tenha saldo bancário.
        # A posição da linha não importa.
        p = pd.Period(mes, freq="M")
        sd = saldos_diarios[
            (saldos_diarios["Data"] >= p.start_time) &
            (saldos_diarios["Data"] <= p.end_time)
        ]

        if not sd.empty:
            ultimo = sd.iloc[-1]
            saldo_real = float(ultimo["Saldo Real"])
            data_saldo = ultimo["Data"]
            origem = ultimo["Origem"]
            ajuste = saldo_real - saldo_calculado
            saldo_final = saldo_real
        else:
            saldo_real = None
            data_saldo = None
            origem = "Calculado"
            ajuste = None
            saldo_final = saldo_calculado

        fundo += r["fundo_liquido"]

        linhas.append({
            "Mês": mes,
            "Saldo Inicial": saldo,
            "Entradas": r["entradas"],
            "Despesas": r["despesas"],
            "Resultado Operacional": r["resultado"],
            "Fundo no Mês": r["fundo_liquido"],
            "Fundo Acumulado": fundo,
            "Movimento Conta Corrente": movimento,
            "Saldo Calculado": saldo_calculado,
            "Saldo Real do Extrato": saldo_real,
            "Ajuste de Conciliação": ajuste,
            "Saldo Final": saldo_final,
            "Data do Saldo Real": data_saldo,
            "Origem do Saldo": origem,
            "Lançamentos": len(g),
        })

        # REGRA PRINCIPAL:
        # fechamento real deste mês = abertura do próximo mês.
        saldo = float(saldo_final)

    return pd.DataFrame(linhas)

df_mensal = cronograma_mensal(lanc, saldo_anterior, SALDO_INICIAL_FUNDO)

# ============================================================
# FILTROS
# ============================================================

st.sidebar.header("🔍 Filtros")

if st.sidebar.button("🔄 Atualizar dados do Drive"):
    st.cache_data.clear()
    st.rerun()

tipo = st.sidebar.selectbox("Tipo de lançamento", ["Todos", "Entrada", "Saída"])
categorias = st.sidebar.multiselect("Categoria", sorted(lanc["Categoria"].unique().tolist()))
meses = st.sidebar.multiselect("Mês", sorted(lanc["Mes"].unique().tolist()))
busca = st.sidebar.text_input("🔎 Pesquisa", placeholder="Fornecedor, lançamento, CNPJ...")

df_filtrado = lanc.copy()

if tipo != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Tipo"] == tipo]
if categorias:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(categorias)]
if meses:
    df_filtrado = df_filtrado[df_filtrado["Mes"].isin(meses)]
if busca:
    mascara = pd.Series(False, index=df_filtrado.index)
    campos = [c for c in [col_lanc, col_razao, col_cnpj] if c] + ["Categoria"]
    for c in dict.fromkeys(campos):
        if c in df_filtrado.columns:
            mascara |= df_filtrado[c].astype(str).str.contains(busca, case=False, na=False, regex=False)
    df_filtrado = df_filtrado[mascara]

# ============================================================
# CABEÇALHO
# ============================================================

col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    try:
        st.image("logo.jpg", width=110)
    except Exception:
        st.write("")
st.title("Condomínio Jardim San Remo")
st.caption("Gestão financeira • Entradas • Saídas • Consumo • Funcionários • Manutenção • Fundo de Reserva • Saldo bancário")

# Conferência especial do período solicitado.
check = lanc[
    (lanc["_Data"] >= pd.Timestamp("2026-04-30")) &
    (lanc["_Data"] <= pd.Timestamp("2026-05-05"))
].copy()

saldo_3004 = saldos_diarios[saldos_diarios["Data"] == pd.Timestamp("2026-04-30")]
saldo_0505 = saldos_diarios[saldos_diarios["Data"] == pd.Timestamp("2026-05-05")]

if not saldo_3004.empty and not saldo_0505.empty:
    saldo_3004_v = float(saldo_3004.iloc[-1]["Saldo Real"])
    saldo_0505_v = float(saldo_0505.iloc[-1]["Saldo Real"])
else:
    saldo_3004_v = None
    saldo_0505_v = None

# KPIs
res = resumo_periodo(df_filtrado)
ultimo_saldo = df_mensal.iloc[-1]["Saldo Final"] if not df_mensal.empty else 0
ultimo_fundo = df_mensal.iloc[-1]["Fundo Acumulado"] if not df_mensal.empty else SALDO_INICIAL_FUNDO

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Entradas", dinheiro(res["entradas"]))
c2.metric("💸 Despesas", dinheiro(res["despesas"]))
c3.metric("📈 Resultado operacional", dinheiro(res["resultado"]))
c4.metric("🏦 Fundo acumulado", dinheiro(ultimo_fundo))
c5.metric("💳 Saldo corrente", dinheiro(ultimo_saldo))

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
    "📋 Dados",
])

# ============================================================
# DASHBOARD
# ============================================================

with tabs[0]:
    st.subheader("📊 Dashboard financeiro")

    if not df_mensal.empty:
        comp = df_mensal.melt(
            id_vars=["Mês"],
            value_vars=["Entradas", "Despesas"],
            var_name="Tipo",
            value_name="Valor",
        )
        fig = px.bar(comp, x="Mês", y="Valor", color="Tipo", barmode="group",
                     title="Entradas x Despesas")
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.line(
            df_mensal,
            x="Mês",
            y=["Saldo Inicial", "Saldo Final"],
            markers=True,
            title="Transposição de saldo mês a mês",
        )
        st.plotly_chart(fig2, use_container_width=True)

        fig3 = px.line(
            df_mensal,
            x="Mês",
            y="Fundo Acumulado",
            markers=True,
            title="Fundo de Reserva acumulado",
        )
        st.plotly_chart(fig3, use_container_width=True)

# ============================================================
# RELATÓRIO MENSAL
# ============================================================

with tabs[1]:
    st.subheader("📅 Relatório mensal — conciliação real")

    cols = [
        "Mês", "Saldo Inicial", "Entradas", "Despesas",
        "Resultado Operacional", "Fundo no Mês", "Fundo Acumulado",
        "Movimento Conta Corrente", "Saldo Calculado",
        "Saldo Real do Extrato", "Ajuste de Conciliação",
        "Saldo Final", "Data do Saldo Real", "Origem do Saldo",
    ]
    view = df_mensal[cols].copy()

    if meses:
        view = view[view["Mês"].isin(meses)]

    st.dataframe(
        view.style.format({
            "Saldo Inicial": dinheiro,
            "Entradas": dinheiro,
            "Despesas": dinheiro,
            "Resultado Operacional": dinheiro,
            "Fundo no Mês": dinheiro,
            "Fundo Acumulado": dinheiro,
            "Movimento Conta Corrente": dinheiro,
            "Saldo Calculado": dinheiro,
            "Saldo Real do Extrato": dinheiro,
            "Ajuste de Conciliação": dinheiro,
            "Saldo Final": dinheiro,
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "Regra: o SALDO FINAL REAL de um mês vira automaticamente o SALDO INICIAL do mês seguinte. "
        "O sistema não usa mais ajuste fixo para 05/05/2026."
    )

    # Conferência explícita pedida pelo usuário.
    st.markdown("### 🔎 Conferência 30/04/2026 → 05/05/2026")
    if saldo_3004_v is not None and saldo_0505_v is not None:
        mov_0505 = check[check["_Data"] == pd.Timestamp("2026-05-05")]["_Valor"].sum()
        calculo = saldo_3004_v + mov_0505
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Saldo 30/04", dinheiro(saldo_3004_v))
        c2.metric("Movimento 05/05", dinheiro(mov_0505))
        c3.metric("Calculado 05/05", dinheiro(calculo))
        c4.metric("Extrato 05/05", dinheiro(saldo_0505_v))

        st.dataframe(
            check[["_Data", col_lanc, col_razao, "_Valor", "Categoria"]]
            .sort_values("_Data")
            .rename(columns={"_Data": "Data", "_Valor": "Valor"}),
            use_container_width=True,
            hide_index=True,
        )

        if abs(calculo - saldo_0505_v) < 0.01:
            st.success("✅ CONFERÊNCIA PERFEITA: R$ 40.451,52 + R$ 11.528,77 = R$ 51.980,29.")
        else:
            st.error(f"❌ Divergência encontrada: {dinheiro(calculo - saldo_0505_v)}.")
    else:
        st.warning("Não foi possível localizar os dois saldos reais no extrato.")

# ============================================================
# PDF
# ============================================================

def tabela_pdf(rows, headers, widths):
    t = Table([headers] + rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
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
    return t

def gerar_pdf(df_mes, dados_mes, mes_nome):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("Titulo", parent=styles["Heading1"], fontSize=18, alignment=TA_CENTER)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12)

    r = resumo_periodo(df_mes)

    story = [
        Paragraph("SAN REMO — RELATÓRIO FINANCEIRO MENSAL", titulo),
        Paragraph(f"Mês: {mes_nome} | Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]),
        Spacer(1, 12),
    ]

    resumo = [
        ["SALDO INICIAL", "ENTRADAS", "DESPESAS", "RESULTADO", "FUNDO ACUM.", "SALDO FINAL"],
        [
            dinheiro(dados_mes["Saldo Inicial"]),
            dinheiro(r["entradas"]),
            dinheiro(r["despesas"]),
            dinheiro(r["resultado"]),
            dinheiro(dados_mes["Fundo Acumulado"]),
            dinheiro(dados_mes["Saldo Final"]),
        ],
    ]
    rt = Table(resumo, colWidths=[120] * 6)
    rt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#CBD5E1")),
    ]))
    story += [rt, Spacer(1, 15)]

    entradas = df_mes[(df_mes["Tipo"] == "Entrada") & (df_mes["Categoria"] != NOME_FUNDO)]
    story.append(Paragraph("1. ENTRADAS", h2))
    if entradas.empty:
        story.append(Paragraph("Nenhuma entrada.", styles["Normal"]))
    else:
        ag = entradas.groupby("Categoria")["Valor_Absoluto"].sum().sort_values(ascending=False)
        rows = [[str(k), dinheiro(v)] for k, v in ag.items()]
        rows.append(["TOTAL DE ENTRADAS", dinheiro(entradas["Valor_Absoluto"].sum())])
        story.append(tabela_pdf(rows, ["Categoria", "Valor"], [600, 150]))

    story.append(Spacer(1, 10))

    despesas = df_mes[(df_mes["Tipo"] == "Saída") & (df_mes["Categoria"] != NOME_FUNDO)]
    story.append(Paragraph("2. DESPESAS OPERACIONAIS", h2))
    if despesas.empty:
        story.append(Paragraph("Nenhuma despesa.", styles["Normal"]))
    else:
        ag = despesas.groupby("Categoria")["Valor_Absoluto"].sum().sort_values(ascending=False)
        rows = [[str(k), dinheiro(v)] for k, v in ag.items()]
        rows.append(["TOTAL DE DESPESAS", dinheiro(despesas["Valor_Absoluto"].sum())])
        story.append(tabela_pdf(rows, ["Categoria", "Valor"], [600, 150]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("3. FUNDO DE RESERVA", h2))
    fundo = df_mes[df_mes["Categoria"] == NOME_FUNDO]
    fundo_val = float(fundo[fundo["Tipo"] == "Saída"]["Valor_Absoluto"].sum())
    story.append(tabela_pdf(
        [["Transferido para o fundo", dinheiro(fundo_val)],
         ["Fundo acumulado", dinheiro(dados_mes["Fundo Acumulado"])]],
        ["Descrição", "Valor"], [600, 150]
    ))

    story.append(Spacer(1, 10))
    story.append(Paragraph("4. CONCILIAÇÃO BANCÁRIA", h2))
    story.append(tabela_pdf(
        [
            ["Saldo inicial", dinheiro(dados_mes["Saldo Inicial"])],
            ["Movimento da conta corrente", dinheiro(dados_mes["Movimento Conta Corrente"])],
            ["Saldo calculado", dinheiro(dados_mes["Saldo Calculado"])],
            ["Saldo real do extrato", dinheiro(dados_mes["Saldo Real do Extrato"]) if pd.notna(dados_mes["Saldo Real do Extrato"]) else "N/D"],
            ["Ajuste", dinheiro(dados_mes["Ajuste de Conciliação"]) if pd.notna(dados_mes["Ajuste de Conciliação"]) else "N/D"],
            ["Saldo final / abertura do próximo mês", dinheiro(dados_mes["Saldo Final"])],
        ],
        ["Item", "Valor"], [600, 150]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer

with tabs[2]:
    st.subheader("📄 PDF Mensal")
    if df_mensal.empty:
        st.warning("Não há dados.")
    else:
        mes_pdf = st.selectbox("Selecione o mês", df_mensal["Mês"].tolist(), index=len(df_mensal)-1)
        dados = df_mensal[df_mensal["Mês"] == mes_pdf].iloc[0]
        df_mes_pdf = lanc[lanc["Mes"] == mes_pdf]
        pdf = gerar_pdf(df_mes_pdf, dados, mes_pdf)

        st.download_button(
            "⬇️ Baixar PDF Mensal",
            data=pdf,
            file_name=f"Relatorio_Mensal_{mes_pdf}.pdf",
            mime="application/pdf",
        )

# ============================================================
# FUNDO
# ============================================================

with tabs[3]:
    st.subheader("🏦 Fundo de Reserva")
    fundo = lanc[lanc["Categoria"] == NOME_FUNDO].copy()
    st.metric("Fundo acumulado", dinheiro(ultimo_fundo))
    if fundo.empty:
        st.info("Nenhuma movimentação de fundo.")
    else:
        st.dataframe(
            fundo[["_Data", col_lanc, "_Valor", "Categoria"]]
            .rename(columns={"_Data": "Data", "_Valor": "Valor"})
            .sort_values("Data"),
            use_container_width=True,
            hide_index=True,
        )

# ============================================================
# SALDO BANCÁRIO
# ============================================================

with tabs[4]:
    st.subheader("🏦 Saldo Bancário / Transposição")

    st.dataframe(
        df_mensal[
            ["Mês", "Saldo Inicial", "Movimento Conta Corrente",
             "Saldo Calculado", "Saldo Real do Extrato",
             "Ajuste de Conciliação", "Saldo Final", "Data do Saldo Real", "Origem do Saldo"]
        ].style.format({
            "Saldo Inicial": dinheiro,
            "Movimento Conta Corrente": dinheiro,
            "Saldo Calculado": dinheiro,
            "Saldo Real do Extrato": dinheiro,
            "Ajuste de Conciliação": dinheiro,
            "Saldo Final": dinheiro,
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Saldos reais encontrados no extrato")
    st.dataframe(
        saldos_diarios.tail(100).style.format({"Saldo Real": dinheiro}),
        use_container_width=True,
        hide_index=True,
    )

# ============================================================
# OUTRAS ABAS
# ============================================================

with tabs[5]:
    st.subheader("👷 Funcionários")
    st.dataframe(
        df_filtrado[df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)],
        use_container_width=True, hide_index=True
    )

with tabs[6]:
    st.subheader("💡 Consumo")
    st.dataframe(
        df_filtrado[df_filtrado["Categoria"].str.startswith("Consumo", na=False)],
        use_container_width=True, hide_index=True
    )

with tabs[7]:
    st.subheader("🛠️ Manutenção")
    st.dataframe(
        df_filtrado[df_filtrado["Categoria"].str.contains(
            "Manutenção|Elevadores|Segurança|Obras|Jardinagem|Piscina|Equipamentos",
            case=False, na=False
        )],
        use_container_width=True, hide_index=True
    )

with tabs[8]:
    st.subheader("💸 Despesas operacionais")
    st.dataframe(
        df_filtrado[(df_filtrado["Tipo"] == "Saída") & (df_filtrado["Categoria"] != NOME_FUNDO)],
        use_container_width=True, hide_index=True
    )

with tabs[9]:
    st.subheader("🔎 Pesquisa")
    st.dataframe(
        df_filtrado.sort_values(["_Data", "_Ordem"]),
        use_container_width=True, hide_index=True
    )

with tabs[10]:
    st.subheader("🧠 Classificação")
    st.dataframe(
        lanc[["Categoria"]].drop_duplicates().sort_values("Categoria"),
        use_container_width=True, hide_index=True
    )

with tabs[11]:
    st.subheader("📋 Dados completos")
    st.dataframe(
        df_filtrado.sort_values(["_Data", "_Ordem"]),
        use_container_width=True, hide_index=True
    )

st.markdown("---")
st.caption(
    "San Remo • Gestão Financeira Condominial | "
    "Saldo real mensal encadeado automaticamente • Sem ajuste fixo de R$ 40.451,52."
)
