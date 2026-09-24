"""Catálogo de máquinas exibido no Início (igual ao site no ar em 24/09/2026).

É o padrão de `providers.get_products`. No projeto real, os produtos devem vir do banco:
aponte `FRONTEND_PRODUCTS_PROVIDER` para uma função que devolva a mesma estrutura.
"""
from decimal import Decimal

_RENTED = "Alugada para operações no campo, com receita compartilhada durante o ciclo."


def _product(code, specs, price, daily_credit, image):
    return {
        "id": code.lower(),
        "code": code,
        "description": f"{specs} {_RENTED}",
        "price": Decimal(price),
        "daily_credit": Decimal(daily_credit),
        "period_days": 16,
        "image": f"frontend/img/produtos/{image}.jpg",
    }


PRODUCTS = [
    _product("NW354", "Máquina de 60 CV, em excelente estado de conservação.", "25", "5", "nw354"),
    _product("NW4050", "Máquina de 85 CV, com tração 4×4.", "50", "10", "nw4050"),
    _product("NW900E", "Máquina de 80 CV, em excelente estado de conservação.", "100", "20", "nw900e"),
    _product("NW765H", "Máquina de 144 CV, com tração 4×4.", "250", "50", "nw765h"),
    _product("NW950R", "Máquina de 122 CV, em excelente estado de conservação.", "500", "100", "nw950r"),
    _product("NW4565H", "Máquina de 201 CV, com motor econômico e alta eficiência.", "750", "150", "nw4565h"),
    _product("NWA4S", "Máquina de 125 CV, com motor econômico e alta eficiência.", "1000", "200", "nwa4s"),
    _product("NWR280", "Máquina de 311 CV, tração 4×4 e transmissão shuttle.", "1500", "300", "nwr280"),
    _product("NW8745F", "Máquina de 170 CV, com excelente torque, tração dianteira auxiliar.", "2000", "400", "nw8745f"),
    _product("NW380SW", "Máquina de 132 CV, com excelente torque.", "3000", "600", "nw380sw"),
    _product("NW550MAG", "Máquina de 193 CV, tração dianteira auxiliar e sistema de engate de 3 pontos.",
             "5000", "1000", "nw550mag"),
    _product("NWRT23K", "Máquina de esteira PR 756, com transmissão hidrostática.", "10000", "2000", "nwrt23k"),
]
