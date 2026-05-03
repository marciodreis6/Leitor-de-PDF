import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime
import os
import base64

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

div[data-testid="stFileUploader"] {{
    max-width: 300px;
}}

.bloco-pequeno {{
    max-width: 300px;
}}
</style>
""", unsafe_allow_html=True)

st.title("📦 Leitor de Remessas")

arquivos = st.file_uploader(
    "Envie os PDFs",
    type="pdf",
    accept_multiple_files=True
)

# ===== LIMPEZA DE NOME =====
def limpar_nome(nome):
    nome = nome.replace("\n", " ")
    nome = re.sub(r'\s+', ' ', nome).strip()

    palavras = nome.split()
    palavras_filtradas = []

    for p in palavras:

        # remove qualquer palavra com número
        if any(char.isdigit() for char in p):
            continue

        # mantém só palavras válidas
        if re.match(r'^[A-Za-zÀ-ÿ&.-]+$', p):
            palavras_filtradas.append(p)

    # remove preposição SOMENTE se estiver no final
    preposicoes = {"DE", "DA", "DO", "DOS", "DAS"}
    if palavras_filtradas and palavras_filtradas[-1].upper() in preposicoes:
        palavras_filtradas.pop()

    return " ".join(palavras_filtradas).strip()

# ===== PROCESSAMENTO =====
def processar_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    blocos = re.split(r'Relat[oó]rio de Manifesto de Carga', texto, flags=re.IGNORECASE)
    dados = []

    agora = datetime.now()
    data = agora.strftime("%d/%m/%Y")
    hora = agora.strftime("%H:%M:%S")

    for bloco in blocos:
        if not re.search(r'Remessa', bloco, re.IGNORECASE):
            continue

        # UNIDADE
        unidade = ""
        if "M432" in bloco:
            unidade = "M432"
        elif "M031" in bloco or "ARATU" in bloco.upper():
            unidade = "M031"

        # REMESSA
        remessa_match = re.search(r'Remessa:\s*0*(\d+)', bloco)
        remessa = remessa_match.group(1) if remessa_match else ""

        # TRANSPORTADORA
        transp = re.search(r'Transportador[a]?:\s*(.*?)\s+Impresso', bloco)
        transportadora = limpar_nome(transp.group(1)) if transp else ""
        transportadora = " ".join(transportadora.split()[:3])

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
        peso = total.group(3) if total else ""
        valor = total.group(4) if total else ""

        # CIDADE
        cidade_match = re.search(r'Cidade:\s*(.*?)(?:Informações|Total|$)', bloco, re.DOTALL)
        cidade = ""
        if cidade_match:
            linhas = cidade_match.group(1).split("\n")
            cidades = [l.strip() for l in linhas if l.strip()]
            cidade = "/".join(dict.fromkeys(cidades))

        # CLIENTE
        clientes = re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s+([A-Z0-9\s\.\-&]+)', bloco)

        clientes_formatados = []
        for c in clientes:
            nome = limpar_nome(c)
            nome = " ".join(nome.split()[:3])
            clientes_formatados.append(nome)

        clientes_unicos = list(set(clientes_formatados))

        if len(clientes_unicos) > 1:
            cliente = "DIVERSOS"
        elif len(clientes_unicos) == 1:
            cliente = clientes_unicos[0]
        else:
            cliente = ""

        # ===== TIPO DE SERVIÇO =====
        cidade_up = cidade.upper()
        cliente_up = cliente.upper()
        transp_up = transportadora.upper()

        if "DUBAI" in cidade_up or "MIAMI" in cidade_up:
            tipo = "EXPORTAÇÃO"
        elif cliente_up == transp_up:
            if "MDIAS" in cliente_up:
                tipo = "TRANSFERENCIA"
            else:
                tipo = "FOB"
        else:
            tipo = "CIF"

        dados.append({
            "UNIDADE": unidade,
            "TIPO DE SERVIÇO": tipo,
            "PRÉ-FAT": "PRÉ-FAT",
            "REMESSA": remessa,
            "TRANSPORTADORA": transportadora,
            "SEGMENTO": "",
            "NOVA AGENDA": "",
            "PESO": peso,
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
    todos = [processar_pdf(a) for a in arquivos]
    df_final = pd.concat(todos, ignore_index=True)

    if not df_final.empty:

        # NÃO MISTURAR UNIDADE
        if df_final["UNIDADE"].nunique() > 1:
            st.error("Mistura de unidades detectada 🚨")

        unidade_final = df_final["UNIDADE"].iloc[0]

        # ordenar clientes (DIVERSOS no final)
        df_final["CLIENTE"] = df_final["CLIENTE"].fillna("")
        df_normais = df_final[df_final["CLIENTE"].str.upper() != "DIVERSOS"]
        df_diversos = df_final[df_final["CLIENTE"].str.upper() == "DIVERSOS"]

        df_normais = df_normais.sort_values(by="CLIENTE", key=lambda x: x.str.upper())
        df_final = pd.concat([df_normais, df_diversos], ignore_index=True)

        # LAYOUT
        if unidade_final == "M031":
            df_final = df_final[[
                "TIPO DE SERVIÇO",
                "REMESSA",
                "TRANSPORTADORA",
                "PESO",
                "VALOR",
                "CLIENTE",
                "LOCAL DE ENTREGA",
                "NF",
                "DATA"
            ]]
        else:
            df_final = df_final[[
                "PRÉ-FAT", "REMESSA", "TRANSPORTADORA",
                "SEGMENTO", "NOVA AGENDA", "PESO",
                "VALOR", "VOLUME", "CLIENTE",
                "LOCAL DE ENTREGA", "NF", "DATA", "HORA"
            ]]

        st.success(f"{len(df_final)} remessas processadas!")

        st.dataframe(df_final, use_container_width=True)

        nome = f"{unidade_final}_prefat_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        df_final.to_excel(nome, index=False)

        with open(nome, "rb") as f:
            st.download_button("📥 Baixar Excel", f, file_name=nome)

    else:
        st.warning("Nenhuma remessa válida encontrada 😅")

else:
    st.info("Envie um PDF pra começar")
