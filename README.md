# CRM Inteligente — Frank Costa Corretora de Seguros

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.x-092E20?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-dados%20relacionais-4169E1?logo=postgresql&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-cotações%20flexíveis-47A248?logo=mongodb&logoColor=white)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)

Plataforma web para a Frank Costa Corretora de Seguros que automatiza a triagem de risco de cotações com um **motor de Inteligência Artificial Simbólica** (sistema especialista, não machine learning) e consolida a operação — clientes, cotações, seguradoras parceiras e apólices — numa arquitetura de **persistência híbrida** (PostgreSQL + MongoDB).

Projeto Integrador II do curso de Big Data para Negócios — FATEC Ipiranga. Os registros usados na demonstração são sintéticos; as seguradoras listadas representam marcas do mercado.

---

## Destaque técnico: motor de IA Simbólica

A triagem de elegibilidade de uma cotação não usa um `if/elif`. É um **sistema especialista real**, com as três camadas clássicas da área:

| Camada | Responsabilidade |
|---|---|
| **Base de Fatos** | o que se sabe do caso (idade, valor do bem) — e os fatos *derivados* durante o raciocínio |
| **Base de Conhecimento** | regras `SE condição ENTÃO conclusão`, escritas como dados (`cotacoes/motor_ia.py`), não como comandos do programa |
| **Motor de Inferência** | encadeamento para frente (*forward chaining*): varre as regras repetidamente e dispara as que se aplicam, até alcançar um parecer |

Cada decisão carrega uma **trilha de inferência** — qual regra disparou, em que ordem, e por quê. Ela apoia a explicabilidade do parecer, mas não representa, por si só, uma certificação de conformidade com a LGPD.

Os campos de automóvel consideram informações usuais para cotação, como marca, modelo, ano, uso, tempo de habilitação, sinistros e eventual condutor adicional. Os limites e pareceres do motor são regras internas de demonstração e não substituem a subscrição nem as tarifas de uma seguradora.

---

## Funcionalidades

- **Gestão de Clientes** — cadastro de pessoas físicas e jurídicas, contatos, endereço, profissão e corretor responsável
- **Catálogo comercial** — tipos de seguro configuráveis e planos ligados a seguradoras, com comissão e atributos de produto opcionais
- **Nova cotação por ramo** — pessoa física pode usar a análise automática de automóvel, vida e saúde; pessoa jurídica gera uma cotação manual sem prêmio calculado
- **Planos de saúde empresariais** — catálogo inicial de produtos SulAmérica e Bradesco Saúde informado pelo usuário, sem preço, CNPJ ou comissão presumidos; Bradesco exige mais de uma vida
- **Cotação com IA Simbólica** — simulação por ramo, parecer explicável e estimativa de prêmio; a comissão só é calculada quando existe percentual cadastrado
- **Gestão da carteira** — cotações relacionais vinculadas às simulações do MongoDB, apólices, renovações, sinistros e recebimentos de comissão
- **Dashboard gerencial** — indicadores e análises interativas de cotações, conversão, carteira, comissões e renovações
- **Back-office via Django Admin** — gestão de clientes, catálogo, cotações, apólices, sinistros, renovações e recebimentos, restrita a usuários staff
- **Autenticação** — todas as telas operacionais exigem login

---

## Painel gerencial Streamlit

O painel `app_analytics.py` integra as cotações do MongoDB e os dados da carteira no PostgreSQL. Os filtros de ramo afetam as cotações e a carteira vigente; período e parecer afetam a análise de cotações, enquanto o período também seleciona receitas demonstrativas e decisões de renovação. A opção **Incluir dados fictícios da demonstração** controla os dados sintéticos identificados pelo projeto.

A tela apresenta comissão bruta demonstrativa mês a mês, tendências de cotações, distribuição de pareceres, conversão, comissões por ramo e seguradora, tabelas pesquisáveis de apólices e renovações e exportação CSV das cotações filtradas. As tabelas exibem até 100 registros; a exportação inclui todos os resultados encontrados. Os dados são atualizados automaticamente a cada minuto ou pelo botão **Atualizar**, que preserva os filtros selecionados.

O painel separa a comissão anual registrada nas apólices ativas do cenário de comissão bruta mensal fictícia. O cenário mensal cobre 24 meses e totaliza entre R$ 6 mil e R$ 12 mil por mês quando os três ramos são selecionados. O líquido médio é uma estimativa com margem acadêmica de 75%; nenhum desses valores representa caixa ou resultado contábil real.

---

## Arquitetura de dados

```
Corretor
   │
   ▼
Formulário de Cotação (Django)
   │
   ├──► Motor de IA Simbólica ──► parecer + trilha de inferência
   │
   ├──► MongoDB (coleção "cotacoes")
   │     simulação completa, schema flexível por tipo de seguro
   │
   ├──► PostgreSQL (Cotação)
   │     status comercial e vínculo com cliente, ramo, plano e simulação
   │
   └──► [Fechar Negócio] ──► PostgreSQL
         Cliente / Bem / Seguradora / Plano / Apólice / Sinistro / Comissão
         registro de contrato, íntegro e transacional (ACID)
```

A escolha híbrida não é estética: o documento completo da simulação mantém flexibilidade no MongoDB. O PostgreSQL também mantém uma cotação relacional resumida, ligada à simulação e às entidades comerciais, para acompanhar status e conversão com integridade referencial. Apólices, sinistros, renovações e recebimentos ficam no PostgreSQL.

O catálogo admite outros ramos além de automóvel, vida e saúde. A análise automática por IA e os formulários específicos estão implementados apenas para esses três; cadastrar outro ramo não implica que já exista regra de cálculo. Valores de comissão podem ficar em branco e, nesse caso, o sistema não estima comissão para a apólice.

Para vincular o histórico já existente no MongoDB às novas cotações relacionais, execute primeiro a prévia `python manage.py migrar_cotacoes_relacionais`; revise a contagem e só então use `python manage.py migrar_cotacoes_relacionais --apply`. O comando é idempotente, preserva os documentos MongoDB e não importa registros sem cliente ou ramo correspondente.

---

## Stack tecnológica

- **Backend:** Django (Python)
- **Banco relacional:** PostgreSQL
- **Banco não-relacional:** MongoDB (via PyMongo)
- **IA Simbólica:** motor de inferência próprio (sem bibliotecas externas de ML)
- **Análise e dashboards:** Pandas + Streamlit + Plotly
- **Frontend:** Django Templates + Bootstrap 5 + Bootstrap Icons

---

## Estrutura do projeto

```
frank-costa-crm/
├── crm_core/                  # configuração do projeto Django
│   ├── settings.py
│   └── urls.py
├── cotacoes/                  # app principal
│   ├── models.py              # catálogo, clientes, cotações e carteira (PostgreSQL)
│   ├── nosql.py                # camada de acesso ao MongoDB
│   ├── motor_ia.py             # sistema especialista (IA Simbólica)
│   ├── utils.py                # normalização de CPF/telefone
│   ├── views.py
│   ├── admin.py
│   ├── templates/cotacoes/
│   ├── static/css/style.css
│   └── management/commands/
│       └── popular_dados.py    # seed de dados fictícios para demonstração
└── manage.py
```

---

## Como rodar localmente

```bash
# 1. Clonar o repositório
git clone https://github.com/Cleverson-Dias/crm-frank-costa.git
cd crm-frank-costa

# 2. Ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# 3. Dependências
pip install -r requirements.txt

# 4. Bancos de dados
#    - Crie um banco PostgreSQL vazio (ex: frank_costa_crm)
#    - Tenha um MongoDB rodando localmente (mongodb://localhost:27017)
#    - Ajuste as credenciais em crm_core/settings.py

# 5. Migrações
python manage.py migrate

# 6. Superusuário (acesso ao /admin/)
python manage.py createsuperuser

# 7. (Opcional) Popular com dados sintéticos para demonstração
#    Cadastre antes planos ativos e percentuais de comissão confirmados
python manage.py popular_dados --limpar

# 8. Rodar
python manage.py runserver

# 9. Em outro terminal, iniciar o painel analítico
python -m streamlit run app_analytics.py
```

Acesse `http://127.0.0.1:8000/` e o painel Streamlit em `http://localhost:8501/`.

---

## Dados de demonstração

O comando `popular_dados` gera, a cada execução, 50 clientes, 50 apólices ativas e 50 cotações adicionais não fechadas, desde que existam planos ativos e percentuais de comissão confirmados para automóvel, vida e saúde. O mix ativo é uma premissa sintética de demonstração: 30 apólices de automóvel, 10 de vida e 10 de saúde. Também cria 48 decisões de renovação distribuídas pelos últimos 24 meses e valores mensais demonstrativos para automóvel, vida e saúde ao longo do mesmo período. O comando não cria seguradoras, identificadores, produtos, coberturas ou percentuais presumidos.

As comissões da carteira são calculadas a partir do percentual cadastrado nos planos. Separadamente, o cenário demonstrativo gera de R$ 6 mil a R$ 12 mil de comissão bruta mensal, com margem líquida acadêmica estimada em 75%. São valores fictícios e não representam dados contábeis nem percentuais reais garantidos pelas seguradoras. A tabela de comissão mensal requer a migração do modelo demonstrativo.

A opção `--limpar` remove clientes e apólices identificados como sintéticos, as cotações marcadas como demonstração e a série de comissões demonstrativas; registros sem essa identificação são preservados. Antes de usá-la em uma base que já contenha dados, confirme que somente os registros demonstrativos desejados estão marcados.

```bash
python manage.py popular_dados --limpar
```

---

## Equipe

- Alexandre Lima André
- Cleverson Alves Dias
- Felipe Santos
- Fernanda da Silva Santos
- Gabriel Willian da Silva

**Curso:** Big Data para Negócios — FATEC Ipiranga "Pastor Enéas Tognini"
**Disciplina:** Projeto Integrador II

---

## Licença

Projeto acadêmico desenvolvido para fins educacionais.
