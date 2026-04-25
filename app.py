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
    </style>
""", unsafe_allow_html=True)

st.title("📦 Leitor de Remessas (PDF → Excel)")

arquivos = st.file_uploader(
    "Envie os PDFs",
    type="pdf",
    accept_multiple_files=True
)

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

        # Remessa (mais tolerante)
        remessa_match = re.search(r'Remessa:\s*0*([0-9]+)', bloco, re.IGNORECASE)

        # Transportadora
        transp = re.search(r'Transportador[a]?:\s*(.*?)\s+Impresso', bloco)
        transportadora = transp.group(1).strip() if transp else ""
        if transportadora:
            transportadora = " ".join(transportadora.split()[:3])

        # NFs
        nfs = re.findall(r'\b(\d{6,})\b', bloco)
        nfs = sorted(set(nfs))
        if not nfs:
            continue

        nf = f"{nfs[0]} a {nfs[-1]}" if len(nfs) > 1 else nfs[0]

        # Totais
        total = re.search(r'Total Geral:\s*(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', bloco)
        volume = total.group(1) if total else ""
        peso_b = total.group(3) if total else ""
        valor = total.group(4) if total else ""

        # Cidade
        cidade_match = re.search(r'Cidade:\s*(.*)', bloco)
        cidade = cidade_match.group(1).strip() if cidade_match else ""

        # ===== CLIENTE ROBUSTO =====
        clientes_encontrados = re.findall(
            r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s+([A-Z0-9\s\.\-&]+)',
            bloco
        )

        clientes_formatados = []
        for c in clientes_encontrados:
            nome = c.replace("\n", " ")
            nome = re.sub(r'\s+', ' ', nome).strip()
            nome = " ".join(nome.split()[:3])
            clientes_formatados.append(nome)

        clientes_unicos = list(set(clientes_formatados))

        if len(clientes_unicos) > 1:
            cliente = "DIVERSOS"
        elif len(clientes_unicos) == 1:
            cliente = clientes_unicos[0]
        else:
            cliente = ""

        # Adiciona linha
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
    todos_dados = []

    for arquivo in arquivos:
        df = processar_pdf(arquivo)
        todos_dados.append(df)

    df_final = pd.concat(todos_dados, ignore_index=True)
    # normaliza
    df_final["CLIENTE"] = df_final["CLIENTE"].fillna("")

    # separa
    df_normais = df_final[df_final["CLIENTE"].str.strip().str.upper() != "DIVERSOS"]
    df_diversos = df_final[df_final["CLIENTE"].str.strip().str.upper() == "DIVERSOS"]

    # ordena só os normais
    df_normais = df_normais.sort_values(by="CLIENTE", key=lambda x: x.str.upper())

    # junta tudo com DIVERSOS no final
    df_final = pd.concat([df_normais, df_diversos], ignore_index=True)
    if not df_final.empty:

        # Ordena por cliente
        df_final = df_final.sort_values(by="CLIENTE").reset_index(drop=True)

        # Ordem das colunas
        colunas = [
            "PRÉ-FAT", "REMESSA", "TRANSPORTADORA", "SEGMENTO",
            "NOVA AGENDA", "PESO", "VALOR", "VOLUME",
            "CLIENTE", "LOCAL DE ENTREGA", "NF", "DATA", "HORA"
        ]

        df_final = df_final[colunas]

        st.success(f"{len(df_final)} remessas processadas!")
        
        col1, col2, col3 = st.columns(3)

        # Converter valores (trocar vírgula por ponto)
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

        nome = f"prefat_{datetime.now().strftime('%d-%m-%Y')}.xlsx"
        df_final.to_excel(nome, index=False)

        with open(nome, "rb") as f:
            st.download_button("📥 Baixar Excel", f, file_name=nome)

        # Copiar só no Windows
        if os.name == "nt":
            import pyperclip
            if st.button("📋 Copiar dados"):
                texto = df_final.to_csv(sep="\t", index=False, header=False)
                pyperclip.copy(texto)
                st.success("Copiado! Só colar 😎")
                st.subheader("📊 Valor por Cliente")

        grafico = df_calc.groupby("CLIENTE")["VALOR"].sum().sort_values(ascending=False)

        st.bar_chart(grafico)

    else:
        st.warning("Nenhuma remessa válida encontrada 😅")

else:
    st.info("Envie um PDF pra começar")
