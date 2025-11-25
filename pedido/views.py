from django.shortcuts import redirect, reverse, get_object_or_404, render
from django.views.generic import ListView, DetailView
from django.views import View
from django.contrib import messages
from django.conf import settings
from . import models

from produto.models import Variacao
from .models import Pedido, ItemPedido
from utils import utils

import stripe

# Configura a chave secreta da Stripe (definida em settings.py)
stripe.api_key = settings.STRIPE_SECRET_KEY


class DispatchLoginRequiredMixin(View):
    def dispatch(self, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return redirect('perfil:criar')
        return super().dispatch(*args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = qs.filter(usuario=self.request.user)
        return qs


class Pagar(DispatchLoginRequiredMixin, DetailView):
    template_name = 'pedido/pagar.html'
    model = Pedido
    pk_url_kwarg = 'pk'
    context_object_name = 'pedido'

    def post(self, request, *args, **kwargs):
        """
        Ao clicar no botão 'Pagar', criamos uma Session do Stripe Checkout
        e redirecionamos o usuário para a página segura de pagamento.
        """
        pedido = self.get_object()

        # Stripe espera valor em centavos (inteiro)
        valor_centavos = int(pedido.total * 100)

        try:
            checkout_session = stripe.checkout.Session.create(
                mode='payment',
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'brl',
                            'product_data': {
                                'name': f'Pedido #{pedido.id}',
                            },
                            'unit_amount': valor_centavos,
                        },
                        'quantity': 1,
                    },
                ],
                metadata={
                    'pedido_id': pedido.id,
                    'user_id': request.user.id,
                },
                success_url=request.build_absolute_uri(
                    reverse('pedido:pagamento_sucesso', kwargs={'pk': pedido.id})
                ) + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=request.build_absolute_uri(
                    reverse('pedido:pagamento_cancelado', kwargs={'pk': pedido.id})
                ),
            )
        except Exception as e:
            messages.error(request, f'Erro ao iniciar pagamento: {e}')
            return redirect('pedido:pagar', pk=pedido.id)

        # Redireciona para a URL do checkout da Stripe
        return redirect(checkout_session.url)


class SalvarPedido(View):
    template_name = 'pedido/pagar.html'

    def get(self, *args, **kwargs):
        if not self.request.user.is_authenticated:
            messages.error(
                self.request,
                'Você precisa fazer login.'
            )
            return redirect('perfil:criar')

        if not self.request.session.get('carrinho'):
            messages.error(
                self.request,
                'Seu carrinho está vazio.'
            )
            return redirect('produto:lista')

        carrinho = self.request.session.get('carrinho')
        carrinho_variacao_ids = [v for v in carrinho]
        bd_variacoes = list(
            Variacao.objects.select_related('produto')
            .filter(id__in=carrinho_variacao_ids)
        )

        # Verifica estoque
        for variacao in bd_variacoes:
            vid = str(variacao.id)

            estoque = variacao.estoque
            qtd_carrinho = carrinho[vid]['quantidade']
            preco_unt = carrinho[vid]['preco_unitario']
            preco_unt_promo = carrinho[vid]['preco_unitario_promocional']

            if estoque < qtd_carrinho:
                carrinho[vid]['quantidade'] = estoque
                carrinho[vid]['preco_quantitativo'] = estoque * preco_unt
                carrinho[vid]['preco_quantitativo_promocional'] = estoque * preco_unt_promo

                messages.error(
                    self.request,
                    'Estoque insuficiente para alguns produtos. Quantidades ajustadas.'
                )
                self.request.session.save()
                return redirect('produto:carrinho')

        # Calcula subtotal do carrinho
        subtotal_carrinho = utils.cart_totals(carrinho)

        # Recupera frete da sessão (NOVO)
        frete = self.request.session.get('frete', 0)

        # Soma frete ao total (NOVO)
        valor_total_carrinho = subtotal_carrinho + frete

        qtd_total_carrinho = utils.cart_total_qtd(carrinho)

        # Cria Pedido com frete incluído (NOVO: frete opcional se tiver campo no modelo)
        pedido = Pedido(
            usuario=self.request.user,
            total=valor_total_carrinho,
            qtd_total=qtd_total_carrinho,
            frete=frete,  # só se o modelo Pedido tiver campo frete
            status='C',  # Criado / Aguardando pagamento
        )
        pedido.save()

        # Cria itens do pedido
        ItemPedido.objects.bulk_create(
            [
                ItemPedido(
                    pedido=pedido,
                    produto=v['produto_nome'],
                    produto_id=v['produto_id'],
                    variacao=v['variacao_nome'],
                    variacao_id=v['variacao_id'],
                    preco=v['preco_quantitativo'],
                    preco_promocional=v['preco_quantitativo_promocional'],
                    quantidade=v['quantidade'],
                    imagem=v['imagem'],
                ) for v in carrinho.values()
            ]
        )

        # Limpa carrinho
        del self.request.session['carrinho']
        self.request.session.save()

        # Redireciona para página de pagamento
        return redirect(
            reverse(
                'pedido:pagar',
                kwargs={'pk': pedido.pk}
            )
        )



class Detalhe(DispatchLoginRequiredMixin, DetailView):
    model = Pedido
    context_object_name = 'pedido'
    template_name = 'pedido/detalhe.html'
    pk_url_kwarg = 'pk'


class Lista(DispatchLoginRequiredMixin, ListView):
    model = Pedido
    context_object_name = 'pedidos'
    template_name = 'pedido/lista.html'
    paginate_by = 10
    ordering = ['-id']


def pagamento_sucesso(request, pk):
    """
    Página de retorno quando a Stripe redireciona após pagamento concluído.
    (Para produção, o ideal é validar via webhook; aqui é atalho para MVP/faculdade.)
    """
    if not request.user.is_authenticated:
        return redirect('perfil:criar')

    pedido = get_object_or_404(Pedido, pk=pk, usuario=request.user)

    # Atalho: marcar como aprovado
    pedido.status = 'A'  # Ex.: "Aprovado"
    pedido.save()

    messages.success(request, 'Pagamento confirmado! Obrigado pela sua compra.')
    return render(request, 'pedido/pagamento_sucesso.html', {'pedido': pedido})


def pagamento_cancelado(request, pk):
    """
    Página de retorno quando o usuário cancela ou não conclui o pagamento na Stripe.
    """
    if not request.user.is_authenticated:
        return redirect('perfil:criar')

    pedido = get_object_or_404(Pedido, pk=pk, usuario=request.user)
    
    pedido.status = 'R'  # Reprovado
    pedido.save()

    messages.warning(
        request,
        'Pagamento não foi concluído. Você pode tentar novamente.'
    )
    return render(request, 'pedido/pagamento_cancelado.html', {'pedido': pedido})


class CancelarPedido(View):

    def post(self, request, pk):
        if not request.user.is_authenticated:
            messages.error(request, 'Você precisa estar logado para cancelar pedidos.')
            return redirect('perfil:criar')

        pedido = get_object_or_404(models.Pedido, pk=pk, usuario=request.user)

        motivo = request.POST.get('motivo', '').strip()  # comentário opcional

        # Status que exigem motivo
        if pedido.status in ['A', 'E'] and not motivo:
            messages.error(request, 'Por favor, informe o motivo do cancelamento.')
            return redirect('pedido:pagar', pk=pedido.pk)

        # Atualiza status do pedido para 'R' (Reprovado/Cancelado)
        pedido.status = 'P'
        if motivo:
            pedido.motivo_cancelamento = motivo  # Campo novo no modelo Pedido
        pedido.save()

        messages.success(request, 'Pedido cancelado com sucesso.')
        return redirect('pedido:lista')
