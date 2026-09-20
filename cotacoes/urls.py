from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("clientes/", views.listar_clientes, name="listar_clientes"),
    path("clientes/novo/", views.novo_cliente, name="novo_cliente"),
    path("cotacao/nova/", views.nova_cotacao, name="nova_cotacao"),
    path("cotacao/<str:cotacao_id>/fechar/", views.fechar_negocio, name="fechar_negocio"),
    path("dashboard/", views.dashboard, name="dashboard"),
]