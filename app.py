import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime
import os
import base64

st.set_page_config(page_title="Leitor de Remessas", layout="wide")


def get_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

img = get_base64("fundo.png")

st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(
            rgba(0, 0, 0, 0.6), 
            rgba(0, 0, 0, 0.6)
        ),
        url("data:image/png;base64,{img}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
    }}
    </style>
""", unsafe_allow_html=True)

st.title("📦 Leitor de Remessas (PDF → Excel)")

arquivos = st.file_uploader(
    "Envie os PDFs",
    type="pdf",
    accept_multiple_files=True
)

def processar_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    blocos = texto.split("Relatório de Manifesto de Carga")
    dados = []

    agora = datetime.now()
    data = agora.strftime("%d/%m/%Y")
    hora = agora.strftime("%H:%M:%S")

    for bloco in blocos:
        if "Nro Remessa" not in bloco:
            continue

        # Remessa
        remessa = re.search(r'Nro Remessa:\s*0*(\d+)', bloco)
        remessa = remessa.group(1) if remessa else ""

        # Transportadora
        transp = re.search(r'Transportadora:\s*(.*?)\s+Impresso', bloco)
        transportadora = transp.group(1).strip() if transp else ""
        if transportadora:
         transportadora = " ".join(transportadora.split()[:3])

        # NFs
        nfs = re.findall(r'\b(11\d{5,})\b', bloco)
        nfs = sorted(set(nfs))

        if not nfs:
            continue

        nf = f"{nfs[0]} a {nfs[-1]}" if len(nfs) > 1 else nfs[0]

        # Total Geral (QT, Peso B, Valor)
        total = re.search(r'Total Geral:\s*(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', bloco)
        
        volume = total.group(1) if total else ""
        peso_b = total.group(3) if total else ""
        valor = total.group(4) if total else ""

        # Cidade
        cidade = re.search(r'Cidade:\s*(.*)', bloco)
        cidade = cidade.group(1).strip() if cidade else ""

        # CLIENTE (corrigido com quebra de linha)
        clientes_encontrados = re.findall(
            r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s+(.+?)(?:\n\s*\n|\d{1,3},\d{3})',
            bloco,
            re.DOTALL
        )

        clientes_formatados = []

        for c in clientes_encontrados:
            nome = c.replace("\n", " ").strip()
            nome = " ".join(nome.split()[:2])  # só 2 palavras
            clientes_formatados.append(nome)

        clientes_unicos = list(set(clientes_formatados))

        if len(clientes_unicos) > 1:
            cliente = "DIVERSOS"
        elif len(clientes_unicos) == 1:
            cliente = clientes_unicos[0]
        else:
            cliente = ""

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

if arquivos:
    todos_dados = []

    for arquivo in arquivos:
        df = processar_pdf(arquivo)
        todos_dados.append(df)

    df_final = pd.concat(todos_dados, ignore_index=True)

    # Ordem correta das colunas
    df_final = df_final[[
        "PRÉ-FAT",
        "REMESSA",
        "TRANSPORTADORA",
        "SEGMENTO",
        "NOVA AGENDA",
        "PESO",
        "VALOR",
        "VOLUME",
        "CLIENTE",
        "LOCAL DE ENTREGA",
        "NF",
        "DATA",
        "HORA"
    ]]

    st.success(f"{len(df_final)} remessas processadas!")

    st.dataframe(df_final, use_container_width=True)

    nome = f"prefat_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
    df_final.to_excel(nome, index=False)

    with open(nome, "rb") as f:
        st.download_button("📥 Baixar Excel", f, file_name=nome)

    if st.button("📋 Copiar dados"):
        texto = df_final.to_csv(sep="\t", index=False, header=False)
        pyperclip.copy(texto)
        st.success("Copiado! Só colar nas cargas pendentes 😎")
else:
    st.info("Copiar automático funciona apenas localmente. Use o download.")
