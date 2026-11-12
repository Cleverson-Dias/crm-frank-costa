# Contexto Geral do Projeto Integrador II - FATEC Ipiranga

## Empresa Parceira
- **Nome:** Frank Costa Corretora de Seguros LTDA.
- **Ramos de Atuação:** Automóvel, Vida e Saúde (SUSEP e ANS).

## Arquitetura Tecnológica
- **Backend & Web Framework:** Django (Python).
- **Interface Web Principal:** Templates HTML/CSS Django com Bootstrap/Custom CSS (`http://127.0.0.1:8000`).
- **Dashboard Executivo / BI:** Streamlit (`app_analytics.py` em `http://localhost:8501`).
- **Banco de Dados Relacional (PostgreSQL):** Dados cadastrais rígidos, integridade referencial, clientes, bens, seguradoras, planos e apólices efetivadas.
- **Banco de Dados NoSQL (MongoDB - `frank_costa_cotacoes`):** Coleção `cotacoes` com documentos JSON flexíveis/schema-less para simulações, subdocumentos por ramo e histórico da trilha de inferência da IA.
- **Integração entre Bancos:** A tabela `cotacoes_apolice` no PostgreSQL guarda o campo `cotacao_mongo_id` referenciando o documento no MongoDB.

## Requisitos Regulatórios
- **LGPD (Art. 20):** Total explicabilidade e auditabilidade das decisões automatizadas da IA.
- **SUSEP & ANS:** Conformidade com prazos legais de carência (24h urgência, 300 dias parto a termo, 180 dias demais), CPT (até 24 meses) e regras de tarifação paramétrica.
