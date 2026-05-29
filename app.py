import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime
import os
import base64
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Leitor de Remessas", layout="wide")

# ===== FUNDO =====
def get_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

img = get_base64("fundo.png")

st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(
            rgba(0, 0, 0, 0.7), 
            rgba(0, 0, 0, 0.7)
        ),
        url("data:image/png;base64,{img}");
        background-size: cover;
        background-position: center;
    }}
    </style>
""", unsafe_allow_html=True)

st.title("📦 Leitor de Remessas")
st.markdown("### PDF → Cargas Pendentes")
st.caption("Faturamento - 432")

st.divider()

col_esq, col_dir = st.columns([1,8])

with col_esq:
    arquivos = st.file_uploader(
        "Envie os relatórios em PDFs",
        type="pdf",
        accept_multiple_files=True
    )

    msg_box = st.empty()
    st.divider()

# ===== LIMPEZA =====
def limpar_nome(nome):
    nome = nome.replace("\n", " ")
    nome = re.sub(r'\s+', ' ', nome).strip()

    # remove números no final
    nome = re.sub(r'\s*\d+$', '', nome)

    palavras = nome.split()

    palavras_filtradas = []

    for i, p in enumerate(palavras):

        # mantém palavras normais
        if len(p) > 3:
            palavras_filtradas.append(p)

        # mantém siglas pequenas SOMENTE no início
        elif i == 0 and len(p) in [1, 2, 3]:
            palavras_filtradas.append(p)

    return " ".join(palavras_filtradas)

# ===== MAPA EXPORTAÇÃO =====
mapa_exportacao = {
    "J W SOLUCOES INTEGRADAS": "WADI BAILOOL GENERAL TRADING CO.",
    "MMA": "TRANSNATIONAL FOODS"
}

# ===== PROCESSAMENTO =====
def processar_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    blocos = re.split(r'Relat[oó]rio de Manifesto de Carga', texto, flags=re.IGNORECASE)
    dados = []

    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    data = agora.strftime("%d/%m/%Y")
    hora = agora.strftime("%H:%M:%S")

    for bloco in blocos:
        if not re.search(r'Remessa', bloco, re.IGNORECASE):
            continue

        # REMESSA
        remessa_match = re.search(r'Remessa:\s*0*(\d+)', bloco)
        remessa = remessa_match.group(1) if remessa_match else ""

        # TRANSPORTADORA
        transp = re.search(r'Transportador[a]?:\s*(.*?)\s+Impresso', bloco)
        transportadora = transp.group(1).strip() if transp else ""

        if transportadora:
            transportadora = limpar_nome(transportadora)
            transportadora = " ".join(transportadora.split()[:4])  # aumentei pra garantir match

        # NFs
        nfs_brutas = re.findall(r'\b\d{6,}\b', bloco)

        nfs = []
        for nf in nfs_brutas:
            nf_limpa = nf.lstrip("0")
            if nf_limpa.startswith("11") or nf_limpa.startswith("16"):
                nfs.append(nf_limpa)

        nfs = sorted(set(nfs))
        if not nfs:
            continue

        nf = f"{nfs[0]} a {nfs[-1]}" if len(nfs) > 1 else nfs[0]

        # TOTAIS
        total = re.search(r'Total Geral:\s*(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', bloco)
        volume = total.group(1) if total else ""
        peso_b = total.group(3) if total else ""
        valor = total.group(4) if total else ""

        # CIDADE
        cidade_match = re.search(r'Cidade:\s*(.*?)(?:Informações|Total|$)', bloco, re.DOTALL)
        cidade = ""

        if cidade_match:
            linhas = cidade_match.group(1).split("\n")
            cidades = [l.strip() for l in linhas if l.strip()]
            cidade = "/".join(dict.fromkeys(cidades))

        # ===== CLIENTE NORMAL =====
        clientes_encontrados = re.findall(
            r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s+(.+?)(?:\n\s*\n|\d{1,3},\d{3})',
            bloco
        )

        clientes_formatados = []
        for c in clientes_encontrados:
            nome = limpar_nome(c)
            # remove qualquer palavra que tenha número
            palavras = nome.split()

            palavras = [
                p for p in palavras
                if not any(char.isdigit() for char in p)
            ]

            nome = " ".join(palavras)
            nome = " ".join(nome.split()[:3])
            clientes_formatados.append(nome)

        clientes_unicos = list(set(clientes_formatados))

        if len(clientes_unicos) > 1:
            cliente = "DIVERSOS"
        elif len(clientes_unicos) == 1:
            cliente = clientes_unicos[0]
        else:
            cliente = ""

        # ===== REGRA EXPORTAÇÃO (AQUI ESTÁ O OURO) =====
        transp_upper = transportadora.upper()

        for chave, cliente_fixo in mapa_exportacao.items():
            if chave in transp_upper:
                cliente = cliente_fixo
                break

        # ===== SALVA =====
        dados.append({
            "PRÉ-FAT": "PRÉ-FAT",
            "REMESSA": remessa,
            "TRANSPORTADORA": transportadora,
            "SEGMENTO": "",
            "NOVA AGENDA": "",
            "PESO": peso_b,
            "VALOR": valor,
            "VOLUME": volume,
            "CLIENTE": cliente,
            "LOCAL DE ENTREGA": cidade,
            "NF": nf,
            "DATA": data,
            "HORA": hora
        })

    return pd.DataFrame(dados)

# ===== EXECUÇÃO =====
if arquivos:
    todos_dados = [processar_pdf(a) for a in arquivos]
    df_final = pd.concat(todos_dados, ignore_index=True)

    df_final["CLIENTE"] = df_final["CLIENTE"].fillna("")

    df_normais = df_final[df_final["CLIENTE"].str.upper() != "DIVERSOS"]
    df_diversos = df_final[df_final["CLIENTE"].str.upper() == "DIVERSOS"]

    df_normais = df_normais.sort_values(by="CLIENTE", key=lambda x: x.str.upper())
    df_final = pd.concat([df_normais, df_diversos], ignore_index=True)

    if not df_final.empty:

        df_final = df_final.sort_values(by="CLIENTE").reset_index(drop=True)

        msg_box.success(f"{len(df_final)} remessas processadas!")

        col1, col2, col3 = st.columns(3)

        df_calc = df_final.copy()
        df_calc["VALOR"] = df_calc["VALOR"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
        df_calc["PESO"] = df_calc["PESO"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)

        with col1:
            st.metric("📦 Remessas", len(df_final))

        with col2:
            st.metric("💰 Valor Total", f"R$ {df_calc['VALOR'].sum():,.2f}")

        with col3:
            st.metric("⚖️ Peso Total", f"{df_calc['PESO'].sum():,.2f} kg")

        st.dataframe(df_final, use_container_width=True)
        
        df_final["DATA"] = df_final["DATA"].astype(str)
        df_final["HORA"] = df_final["HORA"].astype(str)

        nome = f"prefat_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        df_final.to_excel(nome, index=False)

        with open(nome, "rb") as f:
            st.download_button("📥 Baixar planilha", f, file_name=nome)

    else:
        msg_box.warning("Nenhuma remessa válida 😅")

else:
    msg_box.info("Envie um PDF pra começar")
