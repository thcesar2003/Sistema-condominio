import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
import unicodedata
from datetime import datetime

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILOS CSS
# ==========================================
st.set_page_config(
    page_title="Sistema de Gestão Financeira Condominial",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS personalizada para visual executivo
st.markdown("""
<style>
    /* Estilo geral da página */
    .main {
        background-color: #f8fafc;
    }
    
    /* Enfatizar KPIs */
    div[data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 700 !important;
    }
    
    /* Estilo de cartões customizados */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 18px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    /* Abas de navegação */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        background-color: #ffffff;
        border-radius: 8px 8px 0px 0px;
        border: 1px solid #e2e8f0;
        padding: 10px 20px;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #ffffff !important;
    }

    /* Tabelas limpas */
    .dataframe {
        font-size: 14px !important;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. MOTOR DE TRATAMENTO E CATEGORIZAÇÃO
# ==========================================

REGRAS_CATEGORIZACAO_PADRAO = {
    "Consumo - Água e Esgoto": ["SABESP", "ÁGUA", "AGUA", "DAAE", "SANEAMENTO"],
    "Consumo - Energia Elétrica": ["ENEL", "CPFL", "LIGHT", "ELETRO", "ENERGIA", "CEMIG"],
    "Manutenção - Elevadores": ["OTIS", "ATLAS", "SCHINDLER", "ELEVADOR", "THYSSEN"],
    "Manutenção - Portões e Segurança": ["PORTAO", "CÂMERA", "CAMERA", "ALARME", "SEGURANCA", "SEGURANÇA", "CFTV"],
    "Serviços Terceirizados - Portaria e Limpeza": ["PORTARIA", "LIMPEZA", "FACILITIES", "CONSERVAÇÃO", "TERCEIRIZADO"],
    "Despesas Administrativas - Admin/Síndico": ["ADMINISTRADORA", "HONORÁRIOS", "HONORARIOS", "SÍNDICO", "SINDICO", "CONTABILIDADE"],
    "Despesas Financeiras - Tarifas Bancárias": ["TARIFA", "TAXA BANCO", "MANUTENCAO CONTA", "PIX TARIFA", "IOF", "BANCO"],
    "Pessoal - Folha e Encargos": ["SALARIO", "FOLHA", "FGTS", "INSS", "PIS", "VALE REFEICAO", "VT", "BENEFICIO"],
    "Receitas - Cota Condominial": ["CONDOMINIO", "COTA CONDOMINIAL", "TAXA ORDINARIA", "BOLETO", "TAXA CONDOMINIO"],
    "Receitas - Fundo de Reserva": ["FUNDO DE RESERVA", "FUNDO RESERVA"],
    "Receitas - Uso de Áreas Comuns": ["SALÃO DE FESTAS", "CHURRASQUEIRA", "SALAO DE FESTAS", "LOCAÇÃO"],
    "Receitas - Juros e Multas": ["JUROS", "MULTA", "MORA", "ACRÉSCIMO"]
}

def auto_categorizar(descricao, valor_tipo):
    """Categoriza automaticamente o lançamento com base na descrição."""
    if not isinstance(descricao, str):
        return "Outras Despesas" if valor_tipo == "Saída" else "Outras Receitas"
    
    desc_upper = descricao.upper()
    for cat, keywords in REGRAS_CATEGORIZACAO_PADRAO.items():
        for kw in keywords:
            if kw in desc_upper:
                return cat
                
    return "Despesas Diversas" if valor_tipo == "Saída" else "Receitas Diversas"


def normalizar_dataframe(df):
    """Mapeia e padroniza colunas do Excel/CSV carregado com busca robusta sem problemas de acento."""
    df.columns = [str(col).strip() for col in df.columns]
    
    def simplificar(texto):
        texto_norm = unicodedata.normalize('NFD', str(texto))
        return "".join(c for c in texto_norm if unicodedata.category(c) != 'Mn').lower()

    cols_map = {col: simplificar(col) for col in df.columns}
    
    # Mapeamento flexível de colunas
    col_data = next((col for col, s in cols_map.items() if any(x in s for x in ['data', 'dt', 'vencimento', 'periodo'])), None)
    col_desc = next((col for col, s in cols_map.items() if any(x in s for x in ['desc', 'historico', 'lancamento', 'detalhe', 'especificacao', 'histor'])), None)
    col_valor = next((col for col, s in cols_map.items() if any(x in s for x in ['valor', 'val', 'quantia', 'monto', 'saldo'])), None)
    col_tipo = next((col for col, s in cols_map.items() if any(x in s for x in ['tipo', 'natureza', 'operacao', 'e/s', 'cred/deb', 'd/c'])), None)
    col_razao = next((col for col, s in cols_map.items() if any(x in s for x in ['razao', 'nome', 'favorecido', 'pagador', 'recebedor', 'fornecedor', 'cliente'])), None)
    col_cnpj = next((col for col, s in cols_map.items() if any(x in s for x in ['cnpj', 'cpf', 'documento', 'doc'])), None)
    col_cat = next((col for col, s in cols_map.items() if any(x in s for x in ['categoria', 'conta', 'grupo', 'rubrica'])), None)

    df_norm = pd.DataFrame()

    # Processamento de Data
    if col_data:
        df_norm['Data'] = pd.to_datetime(df[col_data], errors='coerce').dt.date
    else:
        df_norm['Data'] = datetime.now().date()

    # Processamento de Descrição
    df_norm['Descrição'] = df[col_desc].astype(str) if col_desc else "Lançamento sem descrição"

    # Processamento de Razão Social
    df_norm['Razão Social'] = df[col_razao].astype(str) if col_razao else "Não Informado"
    df_norm['CNPJ/CPF'] = df[col_cnpj].astype(str) if col_cnpj else "-"

    # Processamento de Valor
    if col_valor:
        if df[col_valor].dtype == object:
            v_clean = df[col_valor].astype(str).str.replace('R$', '', regex=False).str.strip()
            v_clean = v_clean.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
            df_norm['Valor_Orig'] = pd.to_numeric(v_clean, errors='coerce').fillna(0.0)
        else:
            df_norm['Valor_Orig'] = df[col_valor].fillna(0.0)
    else:
        df_norm['Valor_Orig'] = 0.0

    # Processamento de Tipo (Entrada/Saída)
    if col_tipo:
        def classificar_tipo(val):
            v_str = simplificar(val)
            if any(w in v_str for w in ['entrada', 'credito', 'receita', 'cota', 'deposito']):
                return 'Entrada'
            elif any(w in v_str for w in ['saida', 'debito', 'despesa', 'pagamento']):
                return 'Saída'
            elif v_str in ['c', 'e']:
                return 'Entrada'
            elif v_str in ['d', 's']:
                return 'Saída'
            return 'Saída'
        
        df_norm['Tipo'] = df[col_tipo].apply(classificar_tipo)
    elif (df_norm['Valor_Orig'] < 0).any():
        df_norm['Tipo'] = np.where(df_norm['Valor_Orig'] < 0, 'Saída', 'Entrada')
    else:
        def inferir_tipo_por_texto(row):
            texto_completo = f"{row['Descrição']} {row['Razão Social']}".upper()
            palavras_receita = ['CONDOMINIO', 'COTA', 'BOLETO', 'RECEITA', 'FUNDO DE RESERVA', 'TAXA', 'ACRESCIMO', 'JUROS', 'MULTA']
            if any(p in texto_completo for p in palavras_receita):
                return 'Entrada'
            return 'Saída'

        df_norm['Tipo'] = df_norm.apply(inferir_tipo_por_texto, axis=1)

    df_norm['Valor'] = df_norm['Valor_Orig'].abs()
    df_norm.drop(columns=['Valor_Orig'], inplace=True)

    # Processamento de Categoria
    if col_cat:
        df_norm['Categoria'] = df[col_cat].astype(str)
    else:
        df_norm['Categoria'] = [auto_categorizar(desc, tipo) for desc, tipo in zip(df_norm['Descrição'], df_norm['Tipo'])]

    # Ano e Mês para Agrupamentos
    df_norm['Ano_Mês'] = pd.to_datetime(df_norm['Data']).dt.strftime('%Y-%m')

    return df_norm


@st.cache_data
def gerar_dados_exemplo():
    """Gera um extrato demonstrativo completo caso o usuário não tenha arquivo no momento."""
    datas = pd.date_range(start="2026-01-01", end="2026-08-15", freq="D")
    data_list = []
    
    for d in datas:
        if d.day == 10:
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Recebimento Cota Condominial Mês',
                'Tipo': 'Entrada',
                'Valor': 48500.00,
                'Razão Social': 'Condôminos Diversos',
                'CNPJ/CPF': '00.000.000/0001-00',
                'Categoria': 'Receitas - Cota Condominial'
            })
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Arrecadação Fundo de Reserva',
                'Tipo': 'Entrada',
                'Valor': 4850.00,
                'Razão Social': 'Condôminos Diversos',
                'CNPJ/CPF': '00.000.000/0001-00',
                'Categoria': 'Receitas - Fundo de Reserva'
            })

        if d.day == 5:
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Pagamento Folha Salarial Portaria/Zeladoria',
                'Tipo': 'Saída',
                'Valor': 18200.00,
                'Razão Social': 'Funcionários Próprios',
                'CNPJ/CPF': '-',
                'Categoria': 'Pessoal - Folha e Encargos'
            })
        if d.day == 12:
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Fatura Energia Elétrica Áreas Comuns',
                'Tipo': 'Saída',
                'Valor': 3450.80,
                'Razão Social': 'ENEL Distribuição SP',
                'CNPJ/CPF': '61.695.227/0001-93',
                'Categoria': 'Consumo - Energia Elétrica'
            })
        if d.day == 15:
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Manutenção Mensal Elevadores OTIS',
                'Tipo': 'Saída',
                'Valor': 2800.00,
                'Razão Social': 'Elevadores Otis Ltda',
                'CNPJ/CPF': '29.225.096/0001-63',
                'Categoria': 'Manutenção - Elevadores'
            })
        if d.day == 20:
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Fatura Água e Esgoto SABESP',
                'Tipo': 'Saída',
                'Valor': 4120.30,
                'Razão Social': 'SABESP',
                'CNPJ/CPF': '43.776.517/0001-80',
                'Categoria': 'Consumo - Água e Esgoto'
            })
        if d.day == 25:
            data_list.append({
                'Data': d.strftime('%Y-%m-%d'),
                'Descrição': 'Honorários Administradora de Condomínios',
                'Tipo': 'Saída',
                'Valor': 3500.00,
                'Razão Social': 'Alfa Gestão Condominial',
                'CNPJ/CPF': '12.345.678/0001-90',
                'Categoria': 'Despesas Administrativas - Admin/Síndico'
            })

    return pd.DataFrame(data_list)


# ==========================================
# 3. INTERFACE E BARRA LATERAL (SIDEBAR)
# ==========================================
# ==========================================
# CONEXÃO COM O GOOGLE DRIVE
# ==========================================

# Cole aqui a URL de download direto montada no Passo 2
URL_GOOGLE_DRIVE = "https://drive.google.com/uc?export=download&id=1BTYPtjBHLLvSXHH_IfKrnqqwVQZ4hh4T"

@st.cache_data(ttl=300)  # Recarrega os dados do Drive a cada 5 minutos
def carregar_dados_do_drive(url):
    try:
        # Tenta ler como Excel primeiro; se falhar, tenta como CSV
        try:
            df = pd.read_excel(url)
        except Exception:
            df = pd.read_csv(url)
        return normalizar_dataframe(df)
    except Exception as e:
        st.error(f"Erro ao carregar planilha do Google Drive: {e}")
        return None

# --- BARRA LATERAL PARA SELEÇÃO DE FONTE DE DADOS ---
st.sidebar.subheader("📁 Fonte de Dados")
fonte_dados = st.sidebar.radio(
    "Como deseja carregar as informações?",
    ["Google Drive (Automático)", "Fazer Upload de Arquivo"]
)

if fonte_dados == "Google Drive (Automático)":
    if st.sidebar.button("🔄 Atualizar Dados do Drive"):
        st.cache_data.clear()  # Limpa o cache para buscar a versão mais recente
    
    df_dados = carregar_dados_do_drive(URL_GOOGLE_DRIVE)
    
    # CORREÇÃO AQUI: 'is None or' em vez de 'is me ou'
    if df_dados is None or df_dados.empty:
        st.warning("Exibindo dados demonstrativos enquanto a planilha do Drive não for configurada.")
        df_dados = normalizar_dataframe(gerar_dados_exemplo())
else:
    arquivo_uploaded = st.sidebar.file_uploader(
        "Selecione sua planilha Excel (.xlsx) ou CSV",
        type=["xlsx", "xls", "csv"]
    )
    if arquivo_uploaded is not None:
        if arquivo_uploaded.name.endswith('.csv'):
            df_raw = pd.read_csv(arquivo_uploaded)
        else:
            df_raw = pd.read_excel(arquivo_uploaded)
        df_dados = normalizar_dataframe(df_raw)
    else:
        df_dados = normalizar_dataframe(gerar_dados_exemplo())

#novo acima

# --- FILTROS AVANÇADOS NA BARRA LATERAL ---
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros Globais")

# Filtro de Período
min_data = df_dados['Data'].min()
max_data = df_dados['Data'].max()

data_inicio, data_fim = st.sidebar.date_input(
    "Período de Análise",
    value=[min_data, max_data],
    min_value=min_data,
    max_value=max_data
)

# Filtro Tipo
tipos = ["Todos", "Entrada", "Saída"]
tipo_sel = st.sidebar.selectbox("Tipo de Operação", tipos)

# Filtro de Categorias
categorias_disponiveis = ["Todas"] + sorted(list(df_dados['Categoria'].unique()))
categoria_sel = st.sidebar.selectbox("Categoria / Conta", categorias_disponiveis)

# Filtro de Busca Por Texto
busca_termo = st.sidebar.text_input("Buscar Fornecedor, CNPJ ou Histórico", "").strip()

# Aplicação dos Filtros
df_filtrado = df_dados.copy()
df_filtrado = df_filtrado[(df_filtrado['Data'] >= data_inicio) & (df_filtrado['Data'] <= data_fim)]

if tipo_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado['Tipo'] == tipo_sel]

if categoria_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado['Categoria'] == categoria_sel]

if busca_termo:
    mask = (
        df_filtrado['Razão Social'].str.contains(busca_termo, case=False, na=False) |
        df_filtrado['CNPJ/CPF'].str.contains(busca_termo, case=False, na=False) |
        df_filtrado['Descrição'].str.contains(busca_termo, case=False, na=False)
    )
    df_filtrado = df_filtrado[mask]


# ==========================================
# 4. PAINEL PRINCIPAL E NAVEGAÇÃO POR ABAS
# ==========================================

st.title("🏢 Sistema Executivo de Gestão de Condomínio")
st.markdown(f"**Análise de Lançamentos:** de `{data_inicio.strftime('%d/%m/%Y')}` até `{data_fim.strftime('%d/%m/%Y')}`")

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "📊 Dashboard Executivo",
    "📑 Balancete & DRE Condominial",
    "🏭 Curva ABC de Fornecedores",
    "🎯 Orçamento x Realizado",
    "📋 Tabela de Lançamentos & Exportação"
])


# ------------------------------------------
# ABA 1: DASHBOARD EXECUTIVO
# ------------------------------------------
with aba1:
    tot_entradas = df_filtrado[df_filtrado['Tipo'] == 'Entrada']['Valor'].sum()
    tot_saidas = df_filtrado[df_filtrado['Tipo'] == 'Saída']['Valor'].sum()
    resultado_liquido = tot_entradas - tot_saidas
    taxa_cobertura = (tot_entradas / tot_saidas * 100) if tot_saidas > 0 else 100

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

    with col_kpi1:
        st.metric("Total de Receitas (Entradas)", f"R$ {tot_entradas:,.2f}", delta=f"{len(df_filtrado[df_filtrado['Tipo']=='Entrada'])} lançamentos")
    with col_kpi2:
        st.metric("Total de Despesas (Saídas)", f"R$ {tot_saidas:,.2f}", delta=f"-{len(df_filtrado[df_filtrado['Tipo']=='Saída'])} lançamentos", delta_color="inverse")
    with col_kpi3:
        cor_delta = "normal" if resultado_liquido >= 0 else "inverse"
        st.metric("Resultado Líquido do Período", f"R$ {resultado_liquido:,.2f}", delta=f"{'Superávit' if resultado_liquido>=0 else 'Déficit'}", delta_color=cor_delta)
    with col_kpi4:
        st.metric("Índice de Cobertura Financeira", f"{taxa_cobertura:.1f}%", help="Percentual de receitas que cobrem as despesas atuais.")

    st.markdown("---")

    col_graf1, col_graf2 = st.columns([6, 4])

    with col_graf1:
        st.subheader("📈 Evolução Mensal do Fluxo de Caixa")
        df_mensal = df_filtrado.groupby(['Ano_Mês', 'Tipo'])['Valor'].sum().reset_index()
        
        if not df_mensal.empty:
            fig_bar = px.bar(
                df_mensal,
                x='Ano_Mês',
                y='Valor',
                color='Tipo',
                barmode='group',
                color_discrete_map={'Entrada': '#10b981', 'Saída': '#ef4444'},
                labels={'Ano_Mês': 'Mês/Ano', 'Valor': 'Total (R$)'},
                text_auto='.2s'
            )
            fig_bar.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Nenhum dado encontrado para o período selecionado.")

    with col_graf2:
        st.subheader("🍕 Distribuição de Despesas por Categoria")
        df_saidas_cat = df_filtrado[df_filtrado['Tipo'] == 'Saída'].groupby('Categoria')['Valor'].sum().reset_index()
        
        if not df_saidas_cat.empty:
            fig_pie = px.pie(
                df_saidas_cat,
                values='Valor',
                names='Categoria',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sem despesas no período selecionado.")


# ------------------------------------------
# ABA 2: BALANCETE & DRE CONDOMINIAL
# ------------------------------------------
with aba2:
    st.subheader("📑 Demonstrativo de Prestação de Contas (Balancete Sintético)")
    st.caption("Estrutura no padrão oficial utilizado em assembleias ordinárias de condomínio.")

    dre_entradas = df_filtrado[df_filtrado['Tipo'] == 'Entrada'].groupby('Categoria')['Valor'].agg(['sum', 'count']).reset_index()
    dre_entradas.columns = ['Categoria / Rubrica', 'Valor Total (R$)', 'Qtd. Lançamentos']
    
    dre_saidas = df_filtrado[df_filtrado['Tipo'] == 'Saída'].groupby('Categoria')['Valor'].agg(['sum', 'count']).reset_index()
    dre_saidas.columns = ['Categoria / Rubrica', 'Valor Total (R$)', 'Qtd. Lançamentos']

    col_dre1, col_dre2 = st.columns(2)

    with col_dre1:
        st.markdown("### 🟢 RECEITAS (Entradas)")
        if not dre_entradas.empty:
            st.dataframe(
                dre_entradas.style.format({'Valor Total (R$)': 'R$ {:,.2f}'}),
                use_container_width=True,
                hide_index=True
            )
            st.markdown(f"**Total de Receitas:** `R$ {dre_entradas['Valor Total (R$)'].sum():,.2f}`")
        else:
            st.info("Nenhuma receita registrada no período.")

    with col_dre2:
        st.markdown("### 🔴 DESPESAS (Saídas)")
        if not dre_saidas.empty:
            st.dataframe(
                dre_saidas.style.format({'Valor Total (R$)': 'R$ {:,.2f}'}),
                use_container_width=True,
                hide_index=True
            )
            st.markdown(f"**Total de Despesas:** `R$ {dre_saidas['Valor Total (R$)'].sum():,.2f}`")
        else:
            st.info("Nenhuma despesa registrada no período.")

    st.markdown("---")
    
    col_res1, col_res2, col_res3 = st.columns(3)
    col_res1.metric("(=) Total de Entradas", f"R$ {tot_entradas:,.2f}")
    col_res2.metric("(-) Total de Saídas", f"R$ {tot_saidas:,.2f}")
    col_res3.metric("(=) Saldo Operacional do Período", f"R$ {resultado_liquido:,.2f}")


# ------------------------------------------
# ABA 3: CURVA ABC DE FORNECEDORES
# ------------------------------------------
with aba3:
    st.subheader("🏭 Análise de Fornecedores, Prestadores e Favorecidos")
    st.markdown("Identifique onde está concentrada a maior parte dos pagamentos do condomínio (Curva Pareto 80/20).")

    df_fornecedores = df_filtrado[df_filtrado['Tipo'] == 'Saída'].groupby(['Razão Social', 'CNPJ/CPF'])['Valor'].agg(['sum', 'count']).reset_index()
    df_fornecedores.columns = ['Razão Social / Favorecido', 'CNPJ / CPF', 'Total Pago (R$)', 'Nº de Pagamentos']
    df_fornecedores = df_fornecedores.sort_values(by='Total Pago (R$)', ascending=False)

    if not df_fornecedores.empty:
        tot_gastos = df_fornecedores['Total Pago (R$)'].sum()
        df_fornecedores['% do Total'] = (df_fornecedores['Total Pago (R$)'] / tot_gastos) * 100
        df_fornecedores['% Acumulada'] = df_fornecedores['% do Total'].cumsum()

        df_fornecedores['Classificação'] = np.where(df_fornecedores['% Acumulada'] <= 70, 'Classe A (Alto Impacto)',
                                            np.where(df_fornecedores['% Acumulada'] <= 90, 'Classe B (Médio Impacto)', 'Classe C (Baixo Impacto)'))

        col_abc1, col_abc2 = st.columns([7, 3])

        with col_abc1:
            fig_top_forn = px.bar(
                df_fornecedores.head(10),
                x='Total Pago (R$)',
                y='Razão Social / Favorecido',
                orientation='h',
                title="Top 10 Fornecedores com Maior Volume de Pagamentos",
                color='Classificação',
                color_discrete_map={
                    'Classe A (Alto Impacto)': '#ef4444',
                    'Classe B (Médio Impacto)': '#f59e0b',
                    'Classe C (Baixo Impacto)': '#3b82f6'
                }
            )
            fig_top_forn.update_layout(yaxis={'categoryorder':'total ascending'}, height=400)
            st.plotly_chart(fig_top_forn, use_container_width=True)

        with col_abc2:
            st.markdown("#### 💡 Resumo da Curva ABC")
            qtd_a = len(df_fornecedores[df_fornecedores['Classificação'] == 'Classe A (Alto Impacto)'])
            val_a = df_fornecedores[df_fornecedores['Classificação'] == 'Classe A (Alto Impacto)']['Total Pago (R$)'].sum()
            
            st.info(f"**{qtd_a} fornecedores** representam **70% de todo o custo** do condomínio no período, totalizando **R$ {val_a:,.2f}**.")

        st.markdown("#### 📋 Tabela Completa de Fornecedores e Pagadores")
        st.dataframe(
            df_fornecedores.style.format({
                'Total Pago (R$)': 'R$ {:,.2f}',
                '% do Total': '{:.1f}%',
                '% Acumulada': '{:.1f}%'
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhum registro de saída encontrado para os filtros atuais.")


# ------------------------------------------
# ABA 4: ORÇAMENTO X REALIZADO
# ------------------------------------------
with aba4:
    st.subheader("🎯 Comparativo de Orçamento Previsto x Gastos Realizados")
    st.caption("Acompanhe o desvio do orçamento aprovado em assembleia para cada rubrica de despesa.")

    orcamento_estimado = {
        "Consumo - Água e Esgoto": 4500.00,
        "Consumo - Energia Elétrica": 3800.00,
        "Manutenção - Elevadores": 3000.00,
        "Manutenção - Portões e Segurança": 1500.00,
        "Serviços Terceirizados - Portaria e Limpeza": 12000.00,
        "Despesas Administrativas - Admin/Síndico": 3800.00,
        "Despesas Financeiras - Tarifas Bancárias": 400.00,
        "Pessoal - Folha e Encargos": 19000.00,
        "Despesas Diversas": 2000.00
    }

    gastos_reais = df_filtrado[df_filtrado['Tipo'] == 'Saída'].groupby('Categoria')['Valor'].sum().to_dict()

    dados_orcamento = []
    for cat, orc in orcamento_estimado.items():
        realizado = gastos_reais.get(cat, 0.0)
        desvio = realizado - orc
        pct = (realizado / orc * 100) if orc > 0 else 0
        dados_orcamento.append({
            'Categoria': cat,
            'Orçado (R$)': orc,
            'Realizado (R$)': realizado,
            'Diferença (R$)': desvio,
            'Atingido (%)': pct,
            'Status': '🔴 Estourado' if desvio > 0 else '🟢 Dentro do Limite'
        })

    df_orc = pd.DataFrame(dados_orcamento)

    fig_orc = go.Figure()
    fig_orc.add_trace(go.Bar(x=df_orc['Categoria'], y=df_orc['Orçado (R$)'], name='Orçado Previsto', marker_color='#94a3b8'))
    fig_orc.add_trace(go.Bar(x=df_orc['Categoria'], y=df_orc['Realizado (R$)'], name='Realizado', marker_color='#3b82f6'))

    fig_orc.update_layout(barmode='group', title="Comparativo Visual: Previsto vs Realizado", height=400)
    st.plotly_chart(fig_orc, use_container_width=True)

    st.dataframe(
        df_orc.style.format({
            'Orçado (R$)': 'R$ {:,.2f}',
            'Realizado (R$)': 'R$ {:,.2f}',
            'Diferença (R$)': 'R$ {:,.2f}',
            'Atingido (%)': '{:.1f}%'
        }),
        use_container_width=True,
        hide_index=True
    )


# ------------------------------------------
# ABA 5: TABELA DETALHADA E EXPORTAÇÃO
# ------------------------------------------
with aba5:
    st.subheader("📋 Tabela Completa de Lançamentos Filtrados")
    st.markdown(f"Total de **{len(df_filtrado)} lançamentos** encontrados com os filtros aplicados.")

    st.dataframe(
        df_filtrado[['Data', 'Tipo', 'Categoria', 'Descrição', 'Razão Social', 'CNPJ/CPF', 'Valor']],
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")
    st.subheader("📥 Exportação de Relatórios")

    col_exp1, col_exp2 = st.columns(2)

    buffer_excel = io.BytesIO()
    with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
        df_filtrado.to_excel(writer, sheet_name='Extrato Filtrado', index=False)
        dre_saidas.to_excel(writer, sheet_name='Resumo Despesas', index=False)
        dre_entradas.to_excel(writer, sheet_name='Resumo Receitas', index=False)

    col_exp1.download_button(
        label="🟢 Baixar Relatório em Excel (.xlsx)",
        data=buffer_excel.getvalue(),
        file_name=f"relatorio_condominio_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    buffer_csv = df_filtrado.to_csv(index=False, sep=';', encoding='utf-8-sig')
    col_exp2.download_button(
        label="📄 Baixar Extrato em CSV (.csv)",
        data=buffer_csv,
        file_name=f"extrato_condominio_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )