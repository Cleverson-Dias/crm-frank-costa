"""
nosql.py
--------
Camada de persistência NÃO-RELACIONAL (MongoDB) do CRM Frank Costa.

RF02: registrar cotações/simulações com campos dinâmicos por tipo de
seguro (auto, vida, residencial), sem exigir schema rígido.

Cada documento salvo tem esta forma-base (o resto varia por tipo):

{
    "cliente_id": 12,                # FK "solta" para o Postgres
    "bem_id": 7,
    "tipo_seguro": "auto",
    "dados": { ... campos específicos do tipo ... },
    "resultado_calculo": {"premio": 1200.50, "franquia": 800.0, "margem": 180.0},
    "parecer_ia": {"status": "Aprovada", "regra_id": "R03", "motivo": "..."},
    "criado_em": datetime.utcnow(),
}
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import MongoClient
from django.conf import settings

_client = None


def get_db():
    """Retorna a conexão (lazy/singleton) com o banco Mongo do projeto."""
    global _client
    if _client is None:
        # settings.MONGO_URI e settings.MONGO_DB_NAME devem estar em crm_core/settings.py
        _client = MongoClient(settings.MONGO_URI)
    return _client[settings.MONGO_DB_NAME]


def salvar_cotacao(cliente_id, bem_id, tipo_seguro, dados, resultado_calculo, parecer_ia):
    """Persiste uma cotação completa (dados + cálculo + parecer da IA)."""
    db = get_db()
    documento = {
        "cliente_id": cliente_id,
        "bem_id": bem_id,
        "tipo_seguro": tipo_seguro,
        "dados": dados,
        "resultado_calculo": resultado_calculo,
        "parecer_ia": parecer_ia,
        "criado_em": datetime.now(timezone.utc),
    }
    resultado = db.cotacoes.insert_one(documento)
    return str(resultado.inserted_id)


def listar_cotacoes_por_cliente(cliente_id):
    db = get_db()
    return list(db.cotacoes.find({"cliente_id": cliente_id}).sort("criado_em", -1))


def listar_todas_cotacoes(limite=100):
    """Usado pelo dashboard (RF06) para montar os indicadores agregados."""
    db = get_db()
    return list(db.cotacoes.find().sort("criado_em", -1).limit(limite))


def buscar_cotacao_por_id(cotacao_id):
    """
    Busca uma simulação específica pelo ID do Mongo — usada no fluxo
    de "Fechar Negócio", que transforma uma cotação aprovada numa
    Apólice de verdade no Postgres.
    """
    db = get_db()
    return db.cotacoes.find_one({"_id": ObjectId(cotacao_id)})