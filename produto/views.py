from django.shortcuts import render, redirect, reverse, get_object_or_404
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views import View
from django.http import HttpResponse # esse por enquanto nao estou utilizando , mais deixei de segurança caso eu precise
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from utils.frete import calcular_frete


from . import models
from perfil.models import Perfil


class ListaProdutos(ListView):
    model = models.Produto
    template_name = 'produto/lista.html'
    context_object_name = 'produtos'
    paginate_by = 10
    ordering = ['-id']


class Busca(ListaProdutos):
    def get_queryset(self, *args, **kwargs):
        # pega o termo do GET, se não existir tenta da sessão, senão vazio
        termo = self.request.GET.get('termo', '').strip()

        # pega o queryset base da ListView
        qs = super().get_queryset(*args, **kwargs)

        # se não houver termo, retorna todos os produtos
        if not termo:
            # limpa termo antigo da sessão, se existir
            self.request.session.pop('termo', None)
            return qs

        # salva o termo na sessão
        self.request.session['termo'] = termo

        # filtra produtos pelo termo
        qs = qs.filter(
            Q(nome__icontains=termo) |
            Q(descricao_curta__icontains=termo) |
            Q(descricao_longa__icontains=termo)
        )

        self.request.session.save()
        return qs


class DetalheProduto(DetailView):
    model = models.Produto
    template_name = 'produto/detalhe.html'
    context_object_name = 'produto'
    slug_url_kwarg = 'slug'
    
    def get_context_data(self, **kwargs):
        from utils.frete import FRETES 
        contexto = super().get_context_data(**kwargs)

        contexto["cidades"] = [{"nome": c.capitalize()} for c in FRETES.keys()]

        return contexto


class AdicionarAoCarrinho(View):
    def get(self, *args, **kwargs):
        http_referer = self.request.META.get(
            'HTTP_REFERER',
            reverse('produto:lista')
        )
        variacao_id = self.request.GET.get('vid')

        if not variacao_id:
            messages.error(
                self.request,
                'Produto não existe'
            )
            return redirect(http_referer)

        variacao = get_object_or_404(models.Variacao, id=variacao_id)
        variacao_estoque = variacao.estoque
        produto = variacao.produto

        produto_id = produto.id
        produto_nome = produto.nome
        variacao_nome = variacao.nome or ''
        preco_unitario = variacao.preco
        preco_unitario_promocional = variacao.preco_promocional
        quantidade = 1
        slug = produto.slug
        imagem = produto.imagem

        if imagem:
            imagem = imagem.name
        else:
            imagem = ''

        if variacao.estoque < 1:
            messages.error(
                self.request,
                'Estoque insuficiente'
            )
            return redirect(http_referer)

        if not self.request.session.get('carrinho'):
            self.request.session['carrinho'] = {}
            self.request.session.save()

        carrinho = self.request.session['carrinho']

        if variacao_id in carrinho:
            quantidade_carrinho = carrinho[variacao_id]['quantidade']
            quantidade_carrinho += 1

            if variacao_estoque < quantidade_carrinho:
                messages.warning(
                    self.request,
                    f'Estoque insuficiente para {quantidade_carrinho}x no '
                    f'produto "{produto_nome}". Adicionamos {variacao_estoque}x '
                    f'no seu carrinho.'
                )
                quantidade_carrinho = variacao_estoque

            carrinho[variacao_id]['quantidade'] = quantidade_carrinho
            carrinho[variacao_id]['preco_quantitativo'] = preco_unitario * \
                quantidade_carrinho
            carrinho[variacao_id]['preco_quantitativo_promocional'] = preco_unitario_promocional * \
                quantidade_carrinho
        else:
            carrinho[variacao_id] = {
                'produto_id': produto_id,
                'produto_nome': produto_nome,
                'variacao_nome': variacao_nome,
                'variacao_id': variacao_id,
                'preco_unitario': preco_unitario,
                'preco_unitario_promocional': preco_unitario_promocional,
                'preco_quantitativo': preco_unitario,
                'preco_quantitativo_promocional': preco_unitario_promocional,
                'quantidade': 1,
                'slug': slug,
                'imagem': imagem,
            }

        self.request.session.save()

        messages.success(
            self.request,
            f'Produto {produto_nome} {variacao_nome} adicionado ao seu '
            f'carrinho {carrinho[variacao_id]["quantidade"]}x.'
        )

        return redirect(http_referer)


class RemoverDoCarrinho(View):
    def get(self, *args, **kwargs):
        http_referer = self.request.META.get(
            'HTTP_REFERER',
            reverse('produto:lista')
        )
        variacao_id = self.request.GET.get('vid')

        if not variacao_id:
            return redirect(http_referer)

        if not self.request.session.get('carrinho'):
            return redirect(http_referer)

        if variacao_id not in self.request.session['carrinho']:
            return redirect(http_referer)

        carrinho = self.request.session['carrinho'][variacao_id]

        messages.success(
            self.request,
            f'Produto {carrinho["produto_nome"]} {carrinho["variacao_nome"]} '
            f'removido do seu carrinho.'
        )

        del self.request.session['carrinho'][variacao_id]
        self.request.session.save()
        return redirect(http_referer)



class Carrinho(View):
    def get(self, *args, **kwargs):
        carrinho = self.request.session.get('carrinho', {})
        frete = self.request.session.get('frete', 0)

        # calcular subtotal do carrinho
        subtotal = sum(
            item.get('preco_quantitativo_promocional') or item.get('preco_quantitativo')
            for item in carrinho.values()
        )

        total = subtotal + frete

        contexto = {
            'carrinho': carrinho,
            'frete': frete,
            'subtotal': subtotal,
            'total': total,
        }

        return render(self.request, 'produto/carrinho.html', contexto)


class ResumoDaCompra(View):
    def get(self, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return redirect('perfil:criar')

        if not Perfil.objects.filter(usuario=self.request.user).exists():
            messages.error(self.request, 'Usuário sem perfil.')
            return redirect('perfil:criar')

        carrinho = self.request.session.get('carrinho')
        if not carrinho:
            messages.error(self.request, 'Carrinho vazio.')
            return redirect('produto:lista')

        frete = self.request.session.get('frete', 0)

        subtotal = sum(
            item.get('preco_quantitativo_promocional') or item.get('preco_quantitativo')
            for item in carrinho.values()
        )

        total = subtotal + frete

        contexto = {
            'usuario': self.request.user,
            'carrinho': carrinho,
            'frete': frete,
            'subtotal': subtotal,
            'total': total,
        }

        return render(self.request, 'produto/resumodacompra.html', contexto)


def frete(request):
    cidade = request.GET.get("cidade", "")
    valor = calcular_frete(cidade)

    # Salvar na sessão
    request.session["frete"] = valor
    request.session.save()

    return JsonResponse({"frete": valor})

