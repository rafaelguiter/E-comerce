def formata_preco(val):
    try:
        val_float = float(val)
        return f'R$ {val_float:.2f}'.replace('.', ',')
    except (ValueError, TypeError):
        return str(val)


def cart_total_qtd(carrinho):
    return sum([item['quantidade'] for item in carrinho.values()])


def cart_totals(carrinho):
    return sum(
        [
            item.get('preco_quantitativo_promocional')
            if item.get('preco_quantitativo_promocional')
            else item.get('preco_quantitativo')
            for item
            in carrinho.values()
        ]
    )
