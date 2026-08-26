import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import re
import unicodedata
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================
st.set_page_config(
    page_title="San Remo • Gestão Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏢 San Remo • Gestão Financeira Condominial")
st.caption("Painel completo para análise de extratos, despesas, receitas, funcionários e relatórios mensais.")

# ============================================================
# FUNÇÕES AUXILIARES
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
    # Trata formatos brasileiros e números já decimais
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
        "vivo", "claro", "tim", "oi ", "telefonia", "internet", "fibra", "telefon"
    ],
    "Salários": [
        "salario", "salários", "folha", "pagamento funcionario", "pagamento de funcionario",
        "pro labore", "pro-labore"
    ],
    "Funcionários - Encargos": [
        "fgts", "inss", "gps", "e-social", "esocial", "irrf", "contribuicao previdenciaria"
    ],
    "Funcionários - Benefícios": [
        "vale transporte", "vale transporte", "vt ", "vale refeicao", "vale alimentacao",
        "alelo", "ticket", "cesta basica", "beneficio"
    ],
    "Funcionários - Férias/13º": [
        "ferias", "férias", "decimo terceiro", "13 salario", "13º", "abono"
    ],
    "Funcionários - Rescisões": [
        "rescisao", "rescisão", "multa fgts", "aviso previo", "aviso prévio"
    ],
    "Terceirização - Portaria/Segurança": [
        "portaria", "seguranca", "segurança", "vigilancia", "vigia", "controlador de acesso"
    ],
    "Terceirização - Limpeza": [
        "limpeza terceirizada", "conservacao", "conservação", "asseio", "limpeza"
    ],
    "Administradora": [
        "administradora", "assessoria condominial", "gestao condominial", "gestão condominial"
    ],
    "Garantidora": [
        "garantidora", "garantia de recebiveis", "garantia de recebíveis"
    ],
    "Elevadores": [
        "elevador", "elevadores", "qualita", "manutencao elevador"
    ],
    "Manutenção": [
        "manutencao", "manutenção", "conserto", "reparo", "assistencia tecnica", "assistência técnica"
    ],
    "Limpeza/Material": [
        "material de limpeza", "produto de limpeza", "detergente", "desinfetante", "saco de lixo"
    ],
    "Jardinagem": [
        "jardinagem", "jardim", "paisagismo", "poda"
    ],
    "Piscina": [
        "piscina", "cloro", "tratamento piscina"
    ],
    "Segurança Eletrônica": [
        "intelbras", "cftv", "camera", "câmera", "alarme", "monitoramento"
    ],
    "Elevadores/Equipamentos": [
        "bomba", "motor", "gerador", "equipamento"
    ],
    "Obras/Reformas": [
        "obra", "reforma", "pintura", "impermeabilizacao", "impermeabilização", "construcao"
    ],
    "Seguros": [
        "seguro", "apolice", "apólice"
    ],
    "Impostos/Taxas": [
        "tributo", "imposto", "taxa", "iss", "darf", "prefeitura"
    ],
    "Bancárias": [
        "tarifa bancaria", "tarifa bancária", "tarifa", "banco", "ted", "pix tarifa"
    ],
    "Jurídico": [
        "advogado", "advocacia", "juridico", "jurídico", "processo"
    ],
    "Contabilidade": [
        "contabilidade", "contador", "contabil"
    ],
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

def subcategoria_funcionario(categoria):
    return categoria if categoria.startswith("Funcionários") or categoria == "Salários" else ""

# ============================================================
# LEITURA DO ARQUIVO
# ============================================================
uploaded_file = st.sidebar.file_uploader(
    "📥 Carregue o extrato (.xlsx, .xls ou .csv)",
    type=["xlsx", "xls", "csv"]
)

if uploaded_file is None:
    st.info("📌 Carregue o extrato bancário no menu à esquerda para iniciar a análise.")
    st.markdown("""
### O que este painel faz
- 📅 Relatório por mês
- 💧 Contas de consumo separadas
- 👷 Salários e todas as despesas de funcionários
- 🧾 Encargos, benefícios, férias, 13º e rescisões
- 🔎 Pesquisa por fornecedor, CNPJ/CPF, descrição, lançamento e categoria
- 📊 Gráficos e ranking de despesas
- 💰 Comparação de receitas x despesas
- 📤 Exportação dos dados filtrados para Excel e CSV
- 🧠 Classificação automática das despesas
- ✏️ Ajuste manual da categoria dos lançamentos
""")
    st.stop()

try:
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file, sep=None, engine="python")
    else:
        df = pd.read_excel(uploaded_file)
except Exception as e:
    st.error(f"Não foi possível ler o arquivo: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

# ============================================================
# IDENTIFICAÇÃO DAS COLUNAS
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

# Colunas textuais úteis para classificação e pesquisa
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
# FILTROS
# ============================================================
st.sidebar.header("🔍 Filtros avançados")

tipos = ["Todos", "Entrada", "Saída"]
tipo = st.sidebar.selectbox("Tipo de lançamento", tipos)

categorias = sorted(df["Categoria"].dropna().unique().tolist())
categorias_sel = st.sidebar.multiselect(
    "Categoria",
    categorias,
    default=[]
)

meses = sorted(df["Mes"].dropna().unique().tolist())
meses_sel = st.sidebar.multiselect(
    "Mês",
    meses,
    default=[]
)

busca = st.sidebar.text_input(
    "🔎 Pesquisa geral",
    placeholder="Fornecedor, CNPJ, descrição, lançamento..."
)

valor_min = float(df["Valor_Absoluto"].min()) if len(df) else 0
valor_max = float(df["Valor_Absoluto"].max()) if len(df) else 0
faixa = st.sidebar.slider(
    "Faixa de valor (R$)",
    min_value=0.0,
    max_value=max(valor_max, 1.0),
    value=(0.0, max(valor_max, 1.0)),
    step=max(max(valor_max, 1.0) / 100, 0.01)
)

somente_func = st.sidebar.checkbox("👷 Somente despesas de funcionários")
somente_consumo = st.sidebar.checkbox("💡 Somente contas de consumo")

st.sidebar.markdown("---")
st.sidebar.caption("Categorias automáticas podem ser ajustadas na aba 'Classificação'.")

# ============================================================
# APLICAÇÃO DOS FILTROS
# ============================================================
df_filtrado = df.copy()

if tipo != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Tipo_Calculado"] == tipo]

if categorias_sel:
    df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(categorias_sel)]

if meses_sel:
    df_filtrado = df_filtrado[df_filtrado["Mes"].isin(meses_sel)]

if busca:
    mascara = pd.Series(False, index=df_filtrado.index)
    cols_busca = list(dict.fromkeys(colunas_texto + ["Categoria"]))
    for c in cols_busca:
        if c in df_filtrado.columns:
            mascara |= df_filtrado[c].astype(str).str.contains(
                busca, case=False, na=False, regex=False
            )
    df_filtrado = df_filtrado[mascara]

df_filtrado = df_filtrado[
    (df_filtrado["Valor_Absoluto"] >= faixa[0]) &
    (df_filtrado["Valor_Absoluto"] <= faixa[1])
]

if somente_func:
    mask = (
        df_filtrado["Categoria"].str.contains(
            "Salários|Funcionários", case=False, na=False, regex=True
        )
    )
    df_filtrado = df_filtrado[mask]

if somente_consumo:
    mask = df_filtrado["Categoria"].str.startswith("Consumo", na=False)
    df_filtrado = df_filtrado[mask]

# ============================================================
# KPIs
# ============================================================
total_entradas = df_filtrado.loc[
    df_filtrado["Tipo_Calculado"] == "Entrada", col_valor
].sum()

total_saidas = df_filtrado.loc[
    df_filtrado["Tipo_Calculado"] == "Saída", col_valor
].abs().sum()

saldo = total_entradas - total_saidas

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 Entradas", dinheiro(total_entradas))
c2.metric("💸 Despesas", dinheiro(total_saidas))
c3.metric("📈 Resultado", dinheiro(saldo))
c4.metric("📋 Lançamentos", f"{len(df_filtrado):,}".replace(",", "."))
c5.metric("👷 Funcionários", dinheiro(
    df_filtrado[
        df_filtrado["Categoria"].str.contains("Salários|Funcionários", case=False, na=False)
    ]["Valor_Absoluto"].sum()
))

# ============================================================
# ABAS
# ============================================================
tab_dashboard, tab_mensal, tab_func, tab_consumo, tab_despesas, tab_pesquisa, tab_class, tab_dados = st.tabs([
    "📊 Dashboard",
    "📅 Relatório Mensal",
    "👷 Funcionários",
    "💡 Consumo",
    "💸 Despesas",
    "🔎 Pesquisa",
    "🧠 Classificação",
    "📋 Dados"
])

# ============================================================
# DASHBOARD
# ============================================================
with tab_dashboard:
    st.subheader("Visão geral")

    if df_filtrado.empty:
        st.warning("Nenhum lançamento corresponde aos filtros.")
    else:
        col_a, col_b = st.columns(2)

        with col_a:
            resumo_tipo = (
                df_filtrado.groupby("Tipo_Calculado")["Valor_Absoluto"]
                .sum()
                .reset_index()
            )
            fig = px.pie(
                resumo_tipo,
                names="Tipo_Calculado",
                values="Valor_Absoluto",
                hole=0.45,
                title="Entradas x Saídas"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            saidas_cat = (
                df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"]
                .groupby("Categoria")["Valor_Absoluto"]
                .sum()
                .reset_index()
                .sort_values("Valor_Absoluto", ascending=False)
                .head(12)
            )
            fig = px.bar(
                saidas_cat,
                x="Valor_Absoluto",
                y="Categoria",
                orientation="h",
                title="Principais categorias de despesas"
            )
            st.plotly_chart(fig, use_container_width=True)

        if df_filtrado["Data_Analise"].notna().any():
            mensal = (
                df_filtrado[df_filtrado["Data_Analise"].notna()]
                .assign(Mes_dt=df_filtrado["Data_Analise"].dt.to_period("M").dt.to_timestamp())
                .groupby(["Mes_dt", "Tipo_Calculado"])["Valor_Absoluto"]
                .sum()
                .reset_index()
            )
            fig = px.bar(
                mensal,
                x="Mes_dt",
                y="Valor_Absoluto",
                color="Tipo_Calculado",
                barmode="group",
                title="Movimentação por mês"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("🏆 Maiores despesas")
        top = (
            df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"]
            .sort_values("Valor_Absoluto", ascending=False)
            .head(20)
            .copy()
        )
        if not top.empty:
            st.dataframe(top, use_container_width=True, hide_index=True)

# ============================================================
# RELATÓRIO MENSAL
# ============================================================
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
                "Resultado": (
                    g.loc[g["Tipo_Calculado"] == "Entrada", col_valor].sum()
                    - g.loc[g["Tipo_Calculado"] == "Saída", col_valor].abs().sum()
                ),
                "Lançamentos": len(g),
                "Funcionários": g.loc[
                    g["Categoria"].str.contains("Salários|Funcionários", case=False, na=False),
                    "Valor_Absoluto"
                ].sum(),
                "Consumo": g.loc[
                    g["Categoria"].str.startswith("Consumo", na=False),
                    "Valor_Absoluto"
                ].sum(),
            })
        ).reset_index()

        for c in ["Entradas", "Despesas", "Resultado", "Funcionários", "Consumo"]:
            mensal[c] = mensal[c].astype(float)

        st.dataframe(
            mensal.style.format({
                "Entradas": dinheiro,
                "Despesas": dinheiro,
                "Resultado": dinheiro,
                "Funcionários": dinheiro,
                "Consumo": dinheiro,
                "Lançamentos": "{:.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )

        fig = px.line(
            mensal,
            x="Ano_Mes",
            y=["Entradas", "Despesas", "Resultado"],
            markers=True,
            title="Evolução mensal"
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📑 Detalhamento do mês")
        mes_relatorio = st.selectbox("Escolha o mês", sorted(mensal["Ano_Mes"].tolist(), reverse=True))
        dm = d[d["Ano_Mes"] == mes_relatorio].copy()

        categorias_mes = (
            dm[dm["Tipo_Calculado"] == "Saída"]
            .groupby("Categoria")["Valor_Absoluto"]
            .sum()
            .reset_index()
            .sort_values("Valor_Absoluto", ascending=False)
        )
        st.dataframe(categorias_mes, use_container_width=True, hide_index=True)

# ============================================================
# FUNCIONÁRIOS
# ============================================================
with tab_func:
    st.subheader("👷 Despesas de funcionários")

    df_func = df_filtrado[
        df_filtrado["Categoria"].str.contains(
            "Salários|Funcionários", case=False, na=False
        )
    ].copy()

    if df_func.empty:
        st.info("Nenhum lançamento de funcionário encontrado nos filtros atuais.")
    else:
        salario = df_func[
            df_func["Categoria"].isin(["Salários"])
        ]["Valor_Absoluto"].sum()

        encargos = df_func[
            df_func["Categoria"].eq("Funcionários - Encargos")
        ]["Valor_Absoluto"].sum()

        beneficios = df_func[
            df_func["Categoria"].eq("Funcionários - Benefícios")
        ]["Valor_Absoluto"].sum()

        ferias = df_func[
            df_func["Categoria"].eq("Funcionários - Férias/13º")
        ]["Valor_Absoluto"].sum()

        rescisoes = df_func[
            df_func["Categoria"].eq("Funcionários - Rescisões")
        ]["Valor_Absoluto"].sum()

        a, b, c, d, e = st.columns(5)
        a.metric("Salários", dinheiro(salario))
        b.metric("Encargos", dinheiro(encargos))
        c.metric("Benefícios", dinheiro(beneficios))
        d.metric("Férias/13º", dinheiro(ferias))
        e.metric("Rescisões", dinheiro(rescisoes))

        resumo_func = (
            df_func.groupby("Categoria")["Valor_Absoluto"]
            .sum()
            .reset_index()
            .sort_values("Valor_Absoluto", ascending=False)
        )

        fig = px.bar(
            resumo_func,
            x="Categoria",
            y="Valor_Absoluto",
            title="Custo dos funcionários por tipo",
            text_auto=".2f"
        )
        st.plotly_chart(fig, use_container_width=True)

        if df_func["Data_Analise"].notna().any():
            func_mes = (
                df_func[df_func["Data_Analise"].notna()]
                .assign(Ano_Mes=df_func["Data_Analise"].dt.to_period("M").astype(str))
                .groupby("Ano_Mes")["Valor_Absoluto"]
                .sum()
                .reset_index()
            )
            fig = px.bar(func_mes, x="Ano_Mes", y="Valor_Absoluto", title="Custo de funcionários por mês")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_func, use_container_width=True, hide_index=True)

# ============================================================
# CONSUMO
# ============================================================
with tab_consumo:
    st.subheader("💡 Contas de consumo")

    df_cons = df_filtrado[
        df_filtrado["Categoria"].str.startswith("Consumo", na=False)
    ].copy()

    if df_cons.empty:
        st.info("Nenhuma conta de consumo encontrada.")
    else:
        consumo = (
            df_cons.groupby("Categoria")["Valor_Absoluto"]
            .sum()
            .reset_index()
            .sort_values("Valor_Absoluto", ascending=False)
        )

        st.dataframe(
            consumo.style.format({"Valor_Absoluto": dinheiro}),
            use_container_width=True,
            hide_index=True
        )

        fig = px.pie(
            consumo,
            names="Categoria",
            values="Valor_Absoluto",
            hole=0.4,
            title="Distribuição das contas de consumo"
        )
        st.plotly_chart(fig, use_container_width=True)

        if df_cons["Data_Analise"].notna().any():
            cm = (
                df_cons[df_cons["Data_Analise"].notna()]
                .assign(Ano_Mes=df_cons["Data_Analise"].dt.to_period("M").astype(str))
                .groupby(["Ano_Mes", "Categoria"])["Valor_Absoluto"]
                .sum()
                .reset_index()
            )
            fig = px.line(
                cm, x="Ano_Mes", y="Valor_Absoluto", color="Categoria",
                markers=True, title="Evolução mensal do consumo"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_cons, use_container_width=True, hide_index=True)

# ============================================================
# DESPESAS
# ============================================================
with tab_despesas:
    st.subheader("💸 Análise completa das despesas")

    saidas = df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"].copy()

    if saidas.empty:
        st.info("Nenhuma despesa encontrada.")
    else:
        ranking = (
            saidas.groupby("Categoria")
            .agg(
                Total=("Valor_Absoluto", "sum"),
                Quantidade=("Valor_Absoluto", "size"),
                Maior_Lancamento=("Valor_Absoluto", "max")
            )
            .reset_index()
            .sort_values("Total", ascending=False)
        )
        ranking["% do total"] = ranking["Total"] / ranking["Total"].sum() * 100

        st.dataframe(
            ranking.style.format({
                "Total": dinheiro,
                "Maior_Lancamento": dinheiro,
                "% do total": "{:.2f}%"
            }),
            use_container_width=True,
            hide_index=True
        )

        fig = px.bar(
            ranking.head(15),
            x="Total",
            y="Categoria",
            orientation="h",
            title="Ranking das despesas"
        )
        st.plotly_chart(fig, use_container_width=True)

# ============================================================
# PESQUISA
# ============================================================
with tab_pesquisa:
    st.subheader("🔎 Pesquisa detalhada")

    st.write(f"**{len(df_filtrado)} lançamento(s) encontrado(s).**")

    if not df_filtrado.empty:
        st.dataframe(
            df_filtrado.sort_values(
                "Data_Analise", ascending=False, na_position="last"
            ),
            use_container_width=True,
            hide_index=True
        )

        st.subheader("🔍 Resumo da pesquisa")
        res = (
            df_filtrado.groupby(["Tipo_Calculado", "Categoria"])
            .agg(
                Quantidade=(col_valor, "size"),
                Total=("Valor_Absoluto", "sum")
            )
            .reset_index()
            .sort_values("Total", ascending=False)
        )
        st.dataframe(
            res.style.format({"Total": dinheiro}),
            use_container_width=True,
            hide_index=True
        )

# ============================================================
# CLASSIFICAÇÃO MANUAL
# ============================================================
with tab_class:
    st.subheader("🧠 Classificação automática e ajuste manual")

    st.write(
        "O sistema tenta identificar automaticamente fornecedores e descrições. "
        "Se uma despesa estiver classificada incorretamente, você pode editar a categoria abaixo."
    )

    categorias_editaveis = sorted(set(REGRAS.keys()) | {"Outras Despesas", "Receitas"})

    # Para evitar alterar o dataframe principal de forma inesperada, editamos uma cópia.
    classificacao = df[["Categoria_Automatica", "Categoria"]].copy()
    classificacao["Índice"] = classificacao.index
    classificacao = classificacao.drop_duplicates(subset=["Categoria_Automatica", "Categoria"])

    st.dataframe(
        classificacao.sort_values("Categoria_Automatica"),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("### Como melhorar a classificação")
    st.info(
        "Se o seu banco usar nomes muito específicos, me envie um exemplo dos lançamentos. "
        "As regras REGRAS no início do código podem ser ampliadas com fornecedores, CNPJs e palavras-chave."
    )

# ============================================================
# DADOS
# ============================================================
with tab_dados:
    st.subheader("📋 Dados completos")

    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

    # Exportação Excel
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_filtrado.to_excel(writer, index=False, sheet_name="Lancamentos")
        if not df_filtrado.empty:
            (
                df_filtrado.groupby("Categoria")["Valor_Absoluto"]
                .sum()
                .reset_index()
                .sort_values("Valor_Absoluto", ascending=False)
                .to_excel(writer, index=False, sheet_name="Por Categoria")
            )

    st.download_button(
        "⬇️ Baixar Excel filtrado",
        data=excel_buffer.getvalue(),
        file_name="relatorio_condominio_filtrado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    csv_data = df_filtrado.to_csv(index=False, sep=";", encoding="utf-8-sig")
    st.download_button(
        "⬇️ Baixar CSV filtrado",
        data=csv_data,
        file_name="relatorio_condominio_filtrado.csv",
        mime="text/csv"
    )

# ============================================================
# RODAPÉ
# ============================================================
st.markdown("---")
st.caption(
    "San Remo • Gestão Financeira Condominial | "
    "Classificação automática baseada nos dados importados. "
    "Sempre confira a classificação antes de usar os números em prestação de contas."
)
