from django.urls import path
from . import views

app_name = 'pedido'

urlpatterns = [
    # fluxo principal de pedido
    path('salvarpedido/', views.SalvarPedido.as_view(), name='salvarpedido'),
    path('pagar/<int:pk>/', views.Pagar.as_view(), name='pagar'),
    path('lista/', views.Lista.as_view(), name='lista'),
    path('detalhe/<int:pk>/', views.Detalhe.as_view(), name='detalhe'),

    # retorno da Stripe
    path('pagamento-sucesso/<int:pk>/', views.pagamento_sucesso, name='pagamento_sucesso'),
    path('pagamento-cancelado/<int:pk>/', views.pagamento_cancelado, name='pagamento_cancelado'),
    path('cancelar/<int:pk>/', views.CancelarPedido.as_view(), name='cancelar'),
]
