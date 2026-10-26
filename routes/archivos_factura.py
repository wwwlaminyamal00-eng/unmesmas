"""
XML / PDF / CDR de SUNAT guardados en la factura (Erika 26/10/2026: "la opción de descargar el XML, que es lo que
piden los clientes"). La factura se emite en SUNAT (SEE-SOL), que entrega el XML firmado; el ERP no lo puede
firmar, así que aquí se sube una vez y queda para descargarlo cuando el cliente lo pida.
"""
import re

from database import db_query, db_tx

TIPOS = {'.xml': ('XML', 'application/xml'), '.zip': ('ZIP', 'application/zip'), '.pdf': ('PDF', 'application/pdf')}
MAX_BYTES = 5 * 1024 * 1024
_lista = False


class ErrorArchivo(Exception):
    pass


def asegurar_archivos_factura():
    """Tabla comprobante_archivos (migración 033; en la base de pruebas se crea aquí)."""
    global _lista
    if _lista:
        return
    if not db_query("SELECT 1 FROM information_schema.tables WHERE table_name = 'comprobante_archivos'"):
        with db_tx() as conn:
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS comprobante_archivos (
                               id SERIAL PRIMARY KEY,
                               comprobante_id INTEGER NOT NULL,
                               tipo VARCHAR(10) NOT NULL,
                               nombre VARCHAR(150) NOT NULL,
                               mime VARCHAR(80) NOT NULL,
                               datos BYTEA NOT NULL,
                               bytes INTEGER NOT NULL,
                               subido_por VARCHAR(80),
                               created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'America/Lima'))""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_comprobante_archivos_comp ON comprobante_archivos (comprobante_id)")
    _lista = True


def numero_en_xml(texto):
    """Serie y número que dice el XML UBL de SUNAT (primer <cbc:ID> con forma SERIE-NÚMERO)."""
    m = re.search(r'<cbc:ID[^>]*>\s*([A-Z0-9]{4})-0*(\d{1,8})\s*</cbc:ID>', texto or '')
    return (m.group(1), int(m.group(2))) if m else None


def guardar_archivo(comp, archivo, usuario):
    """Valida y guarda el archivo. comp: fila del comprobante (id, serie, numero)."""
    if not archivo or not archivo.filename:
        raise ErrorArchivo('Elige el archivo XML (o PDF/ZIP) que te dio SUNAT.')
    nombre = archivo.filename.strip()[:150]
    ext = ('.' + nombre.rsplit('.', 1)[-1].lower()) if '.' in nombre else ''
    if ext not in TIPOS:
        raise ErrorArchivo('Solo se aceptan archivos .xml, .zip o .pdf de SUNAT.')
    datos = archivo.read(MAX_BYTES + 1)
    if len(datos) > MAX_BYTES:
        raise ErrorArchivo('El archivo pesa más de 5 MB.')
    if not datos:
        raise ErrorArchivo('El archivo está vacío.')
    tipo, mime = TIPOS[ext]
    if tipo == 'XML':
        texto = datos.decode('utf-8', errors='ignore')
        if '<' not in texto[:200]:
            raise ErrorArchivo('Ese archivo no es un XML.')
        dice = numero_en_xml(texto)
        try:
            esperado = (str(comp.get('serie') or '').strip().upper(), int(str(comp.get('numero') or '0')))
        except ValueError:
            esperado = None
        if dice and esperado and dice != esperado:
            raise ErrorArchivo(f'Ese XML es de la factura {dice[0]}-{dice[1]:08d}, no de '
                               f'{esperado[0]}-{esperado[1]:08d}. Revisa que sea el correcto.')
    with db_tx() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO comprobante_archivos (comprobante_id, tipo, nombre, mime, datos, bytes, subido_por)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (comp['id'], tipo, nombre, mime, datos, len(datos), usuario))
        aid = cur.fetchone()[0]
    return {'id': aid, 'tipo': tipo, 'nombre': nombre, 'bytes': len(datos)}


def listar_archivos(comp_id):
    return db_query("""SELECT id, tipo, nombre, bytes, subido_por, created_at FROM comprobante_archivos
                       WHERE comprobante_id = %s ORDER BY id DESC""", (comp_id,))


def leer_archivo(aid):
    filas = db_query("SELECT id, comprobante_id, nombre, mime, datos FROM comprobante_archivos WHERE id = %s", (aid,))
    return filas[0] if filas else None
