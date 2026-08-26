import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata

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
    st.caption("Painel completo para análise de extratos, despesas, receitas, funcionários e relatórios mensais.")

st.markdown("---")

# ============================================================
# FUNÇÕES DE AUXÍLIO E CLASSIFICAÇÃO AUTOMÁTICA
# ============================================================
def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_str = str(texto).lower().strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto_str)
        if unicodedata.category(c) != "Mn"
    )

def encontrar_coluna(df, candidatos):
    colunas_norm = {col: normalizar_texto(col) for col in df.columns}
    for cand in candidatos:
        cand_norm = normalizar_texto(cand)
        for col_orig, col_n in colunas_norm.items():
            if cand_norm in col_n:
                return col_orig
    return None

def limpar_valor(serie):
    if serie.dtype == "object":
        serie_limpa = (
            serie.astype(str)
            .str.replace("R$", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        return pd.to_numeric(serie_limpa, errors="coerce")
    return pd.to_numeric(serie, errors="coerce")

def classificar_linha(row, col_lancamento, col_cnpj, col_razao, col_valor):
    lancamento = normalizar_texto(row.get(col_lancamento, ""))
    cnpj = str(row.get(col_cnpj, "")).strip()
    razao = normalizar_texto(row.get(col_razao, ""))
    valor = row.get(col_valor, 0)

    # 1. Aplicação Privilege INT -> Fundo de Reserva
    if "aplicacao privilege int" in lancamento or "privilege int" in lancamento:
        return "Fundo de Reserva"

    # 2. CNPJ 51.877.768/0001-89 -> Mercadinho
    if "51.877.768/0001-89" in cnpj or "51877768000189" in cnpj.replace(".", "").replace("/", "").replace("-", ""):
        return "Mercadinho"

    # 3. Entrada de R$ 150,00 -> Salão de Festas
    if valor == 150.0:
        return "Salão de Festas"

    # 4. Universal Telecom ou Directnet -> Antenas
    if any(termo in razao or termo in lancamento for termo in ["universal telecom", "directnet"]):
        return "Antenas"

    # Demais regras padrão
    if "rendimento" in lancamento or "rend pto" in lancamento:
        return "Rendimentos"
    elif "boleto" in lancamento:
        return "Boletagem / Tarifas"
    elif "pix" in lancamento:
        return "PIX / Transferências"
    
    return "Outros"

# ============================================================
# LEITURA E TRATAMENTO AUTOMÁTICO DO GOOGLE DRIVE
# ============================================================
url = "https://drive.google.com/uc?export=download&id=1BTYPtjBHLLvSXHH_IfKrnqqwVQZ4hh4T"

@st.cache_data(ttl=300)
def carregar_dados():
    df_raw = pd.read_excel(url, header=None)
    linha_cabecalho = 0
    for idx, row in df_raw.iterrows():
        linha_texto = " ".join([normalizar_texto(val) for val in row.values if pd.notna(val)])
        if "valor" in linha_texto or "data" in linha_texto or "lancamento" in linha_texto:
            linha_cabecalho = idx
            break
            
    df_final = pd.read_excel(url, header=linha_cabecalho)
    return df_final

try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Não foi possível ler o arquivo do Google Drive: {e}")
    st.stop()

df.columns = [str(c).strip() for c in df.columns]

# Identificação dinâmica de colunas
col_valor = encontrar_coluna(df, ["valor", "valor r$", "valor (r$)", "amount"])
col_data = encontrar_coluna(df, ["data", "data lançamento", "data lancamento", "date"])
col_lanc = encontrar_coluna(df, ["lançamento", "lancamento", "histórico", "historico"])
col_cnpj = encontrar_coluna(df, ["cpf/cnpj", "cpf", "cnpj", "documento"])
col_razao = encontrar_coluna(df, ["razão social", "razao social", "fornecedor", "favorecido"])

if not col_valor:
    st.error("❌ Não foi encontrada a coluna de valor no arquivo.")
    st.stop()

# Tratamento dos dados
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

# Aplicação da classificação por linha
df["Categoria"] = df.apply(
    lambda r: classificar_linha(r, col_lanc, col_cnpj, col_razao, col_valor),
    axis=1
)

df["Mes"] = df["Data_Analise"].dt.to_period("M").astype(str)
df.loc[df["Mes"] == "NaT", "Mes"] = "Sem data"

# ============================================================
# FILTROS NA BARRA LATERAL
# ============================================================
st.sidebar.header("🔍 Filtros de Análise")

meses_disponiveis = sorted(df["Mes"].unique().tolist())
meses_selecionados = st.sidebar.multiselect("Mês", meses_disponiveis, default=meses_disponiveis)

tipos_disponiveis = df["Tipo_Calculado"].unique().tolist()
tipos_selecionados = st.sidebar.multiselect("Tipo de Operação", tipos_disponiveis, default=tipos_disponiveis)

categorias_disponiveis = sorted(df["Categoria"].unique().tolist())
categorias_selecionadas = st.sidebar.multiselect("Categoria", categorias_disponiveis, default=categorias_disponiveis)

# Aplicar Filtros
df_filtrado = df[
    (df["Mes"].isin(meses_selecionados)) &
    (df["Tipo_Calculado"].isin(tipos_selecionados)) &
    (df["Categoria"].isin(categorias_selecionadas))
]

if st.sidebar.button("🔄 Atualizar Dados do Drive"):
    st.cache_data.clear()
    st.rerun()

# ============================================================
# MENU PRINCIPAL COM ABAS
# ============================================================
tab_dashboard, tab_extrato = st.tabs(["📊 Dashboard", "📄 Extrato Detalhado"])

# 📊 ABA 1: DASHBOARD
with tab_dashboard:
    st.subheader("Visão Geral Financeira")

    if df_filtrado.empty:
        st.warning("Nenhum lançamento corresponde aos filtros selecionados.")
    else:
        # Gráfico 1: Comparativo Mensal de Entradas e Saídas
        df_com_data = df_filtrado[df_filtrado["Data_Analise"].notna()].copy()

        if not df_com_data.empty:
            df_com_data["Ano_Mes"] = df_com_data["Data_Analise"].dt.to_period("M").astype(str)
            
            mensal_comparativo = (
                df_com_data[df_com_data["Tipo_Calculado"].isin(["Entrada", "Saída"])]
                .groupby(["Ano_Mes", "Tipo_Calculado"])["Valor_Absoluto"]
                .sum()
                .reset_index()
            )

            fig_mensal = px.bar(
                mensal_comparativo,
                x="Ano_Mes",
                y="Valor_Absoluto",
                color="Tipo_Calculado",
                barmode="group",
                title="📊 Comparativo Mensal: Entradas x Saídas",
                labels={"Ano_Mes": "Mês", "Valor_Absoluto": "Valor (R$)", "Tipo_Calculado": "Tipo"},
                color_discrete_map={"Entrada": "#10B981", "Saída": "#EF4444"},
                text_auto=".2s"
            )
            fig_mensal.update_layout(xaxis_type='category', height=400)
            st.plotly_chart(fig_mensal, use_container_width=True)

        st.markdown("---")

        # Gráficos 2 e 3: Pizza e Top Categorias
        col_a, col_b = st.columns(2)

        with col_a:
            resumo_tipo = df_filtrado.groupby("Tipo_Calculado")["Valor_Absoluto"].sum().reset_index()
            fig_pie = px.pie(
                resumo_tipo,
                names="Tipo_Calculado",
                values="Valor_Absoluto",
                hole=0.45,
                title="Proporção de Entradas x Saídas",
                color="Tipo_Calculado",
                color_discrete_map={"Entrada": "#10B981", "Saída": "#EF4444", "Neutro": "#6B7280"}
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_b:
            saidas_cat = (
                df_filtrado[df_filtrado["Tipo_Calculado"] == "Saída"]
                .groupby("Categoria")["Valor_Absoluto"]
                .sum()
                .reset_index()
                .sort_values("Valor_Absoluto", ascending=True)
                .tail(10)
            )
            fig_bar_cat = px.bar(
                saidas_cat,
                x="Valor_Absoluto",
                y="Categoria",
                orientation="h",
                title="Top Categorias de Despesas",
                labels={"Valor_Absoluto": "Valor (R$)", "Categoria": ""},
                color_discrete_sequence=["#1E3A8A"]
            )
            st.plotly_chart(fig_bar_cat, use_container_width=True)

# 📄 ABA 2: EXTRATO DETALHADO
with tab_extrato:
    st.subheader("Tabela de Lançamentos")
    st.dataframe(df_filtrado, use_container_width=True)