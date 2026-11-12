# Padrões de Código e Tratamento de Dados

## Tratamento Defensivo em Python (Evitar Crashes)
- Sempre tratar dicionários do MongoDB usando `.get()` ou `isinstance(dict)` para evitar `TypeError: 'NoneType' object is not subscriptable`.
- Tratar dados nulos/ausentes em consultas e agregar métricas de forma segura.

## Convenção de Commits (Conventional Commits)
- `feat:` Novas funcionalidades.
- `fix:` Correção de bugs.
- `style:` Alterações de visual/CSS/layout sem mexer na lógica.
- `refactor:` Reorganização de código.
- `docs:` Alterações na documentação.
- `chore:` Manutenção e dependências.

## Padrão de Execução
- Servidor Django: `python manage.py runserver`
- Dashboard Streamlit: `python -m streamlit run app_analytics.py`