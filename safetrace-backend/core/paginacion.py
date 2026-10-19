"""Paginación de historiales: máximo 50 registros por página (RNF-30).

Uso en una ruta:
    def listar(pagina: Pagina = Depends(), ...):
        datos, total = crud.listar(db, saltar=pagina.saltar, limite=pagina.tamano)
        return pagina.respuesta(datos, total)
"""

from pydantic import BaseModel, Field


class Pagina(BaseModel):
    pagina: int = Field(1, ge=1)
    tamano: int = Field(20, ge=1, le=50)

    @property
    def saltar(self) -> int:
        return (self.pagina - 1) * self.tamano

    def respuesta(self, datos: list, total: int) -> dict:
        return {
            "pagina": self.pagina,
            "tamano": self.tamano,
            "total": total,
            "total_paginas": (total + self.tamano - 1) // self.tamano,
            "datos": datos,
        }
