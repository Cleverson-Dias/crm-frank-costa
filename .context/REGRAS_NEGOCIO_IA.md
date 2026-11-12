# Regras de Negócio do Motor de IA Simbólica (`cotacoes/motor_ia.py`)

## Arquitetura da IA
- **Tipo:** IA Simbólica / Sistema Especialista com Encadeamento para Frente (Forward Chaining).
- **Funcionamento:** Recebe a base de fatos (perfil do condutor/segurado, bem) -> Executa regras de classificação (prefixo `C-`) -> Dispara a regra de parecer de maior prioridade (prefixo `R-` para Auto, `V-` para Vida, `S-` para Saúde) -> Gera a `trilha_inferencia`.
- **Explicabilidade:** Nunca aceitar abordagens "caixa-preta". Toda decisão deve registrar a regra disparada, o motivo e a trilha no MongoDB.

## Motores Independentes
1. **Automóvel (SUSEP):** Avalia idade (18-24 com agravo, <18 recusa), valor FIPE (>R$ 500k vistoria), idade do veículo (>15 anos vistoria), histórico de sinistros.
2. **Vida (SUSEP):** Avalia DPS (Declaração Pessoal de Saúde), idade limite, capital segurado e risco ocupacional.
3. **Saúde (ANS):** Valida elegibilidade por segmentação, prazos de carência (24h Urgência/Emergência, 300d Parto a termo, 180d Demais) e aplicação de CPT (Cobertura Parcial Temporária).