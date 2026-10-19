"""
Fechas en las respuestas JSON del ERP, siempre en hora de Lima (17/10/2026).

Antes Flask mandaba las fechas como "Fri, 16 Oct 2026 14:47:48 GMT": decía GMT aunque la hora
guardada ya era la de Lima, y el navegador le restaba 5 horas al mostrarla. Ahora se manda
"2026-10-16T14:47:48" (sin zona): el navegador la muestra tal cual, es decir, en hora de Lima.
Las fechas con zona (timestamptz) se pasan primero a hora de Lima. Las fechas sin hora salen
como "2026-10-16".
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from flask.json.provider import DefaultJSONProvider

from database import ZONA_HORARIA

LIMA = ZoneInfo(ZONA_HORARIA)


def fecha_json(valor):
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.astimezone(LIMA).replace(tzinfo=None)
        return valor.isoformat(timespec='seconds')
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, time):
        return valor.replace(tzinfo=None).isoformat(timespec='minutes')
    return None


class ProveedorJSONLima(DefaultJSONProvider):
    @staticmethod
    def default(o):
        texto = fecha_json(o)
        if texto is not None:
            return texto
        return DefaultJSONProvider.default(o)


def instalar(app):
    app.json_provider_class = ProveedorJSONLima
    app.json = ProveedorJSONLima(app)
