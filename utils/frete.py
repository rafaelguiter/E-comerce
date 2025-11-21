FRETES = {
    "são paulo": 19.90,
    "rio de janeiro": 24.90,
    "salvador": 29.90,
    "bh": 22.50,
    "belo horizonte": 22.50,
    "fortaleza": 27.90,
    "manaus": 39.90,
    "curitiba": 21.90,
    "recife": 28.90,
    "brasilia - df": 20.00,
}

def calcular_frete(cidade: str) -> float:
    if not cidade:
        return 39.90
    cidade = cidade.lower().strip()
    return FRETES.get(cidade, 39.90)


