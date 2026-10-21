import json
import sys

from database import (
    crear_usuario,
    insertar_cliente,
    insertar_contacto_cliente,
    insertar_punto_entrega,
    insertar_producto,
    insertar_proveedor
)


from psycopg2 import IntegrityError


def safe_run(label, fn, *args, **kwargs):
    """Ejecuta inserción y si choca con UNIQUE, lo omite."""
    try:
        return fn(*args, **kwargs)
    except IntegrityError:
        print(f"⚠️ Omitido (ya existe): {label}")
        return None


def load_seed(path: str):

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 👇 Usuarios
    for u in data.get("usuarios", []):
        safe_run(
            f"usuario={u.get('usuario')}",
            crear_usuario,
            usuario=u["usuario"],
            password=u["password"],
            rol=u["rol"],
            nombre_completo=u["nombre_completo"],
            email=u.get("email", "")
        )

    # 👇 Proveedores
    for p in data.get("proveedores", []):
        safe_run(
            f"proveedor ruc={p.get('ruc')}",
            insertar_proveedor,
            razon_social=p["razon_social"],
            ruc=p["ruc"],
            direccion=p["direccion"],
            telefono=p.get("telefono", ""),
            contacto=p.get("contacto", ""),
            email=p.get("email", "")
        )

    # 👇 Productos
    for pr in data.get("productos", []):
        safe_run(
            f"producto desc={pr.get('descripcion')}",
            insertar_producto,
            familia=pr["familia"],
            descripcion=pr["descripcion"],
            descripcion_larga=pr.get("descripcion_larga", ""),
            marca=pr.get("marca", ""),
            modelo=pr.get("modelo", ""),
            unidad=pr.get("unidad", "Unidad")
        )

    # 👇 Clientes
    for c in data.get("clientes", []):
        cliente_id = safe_run(
            f"cliente doc={c.get('numero_documento')}",
            insertar_cliente,
            tipo_documento=c["tipo_documento"],
            numero_documento=c["numero_documento"],
            razon_social=c["razon_social"],
            direccion_fiscal=c["direccion_fiscal"]
        )

        if not cliente_id:
            continue

        # 👇 Contactos
        for cc in c.get("contactos", []):
            safe_run(
                f"contacto cliente_id={cliente_id}",
                insertar_contacto_cliente,
                cliente_id=cliente_id,
                nombre_contacto=cc["nombre_contacto"],
                email=cc.get("email", ""),
                telefono=cc.get("telefono", ""),
                cargo=cc.get("cargo", ""),
                principal=cc.get("principal", False)
            )

        # 👇 Puntos de entrega
        for pe in c.get("puntos_entrega", []):
            safe_run(
                f"punto_entrega cliente_id={cliente_id}",
                insertar_punto_entrega,
                cliente_id=cliente_id,
                nombre_punto=pe["nombre_punto"],
                direccion=pe["direccion"],
                departamento=pe.get("departamento", ""),
                provincia=pe.get("provincia", ""),
                distrito=pe.get("distrito", ""),
                telefono_contacto=pe.get("telefono_contacto", ""),
                responsable=pe.get("responsable", ""),
                principal=pe.get("principal", False)
            )

    print("✅ Seed cargado correctamente en PostgreSQL.")


def main():
    if len(sys.argv) < 2:
        print("Uso: python seed_loader.py seed_data.json")
        sys.exit(1)

    seed_path = sys.argv[1]
    load_seed(seed_path)


if __name__ == "__main__":
    main()