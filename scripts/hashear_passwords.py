"""
Convierte las contraseñas guardadas en TEXTO PLANO en la tabla usuarios a hash seguro (scrypt).
Los usuarios siguen entrando con la MISMA contraseña; solo cambia cómo se guarda.

Uso (desde la carpeta del proyecto, con el .env configurado):
    python scripts/hashear_passwords.py            -> solo muestra cuántos usuarios se convertirían
    python scripts/hashear_passwords.py --aplicar  -> realiza la conversión

Recomendación: hacer antes un respaldo de la base desde Supabase (Database > Backups).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from werkzeug.security import generate_password_hash  # noqa: E402
from database import db_query, db_tx  # noqa: E402

PREFIJOS_HASH = ('scrypt:', 'pbkdf2:', '$2a$', '$2b$', '$2y$')


def main():
    aplicar = '--aplicar' in sys.argv
    usuarios = db_query("SELECT id, usuario_sistema, password FROM usuarios WHERE password IS NOT NULL AND password <> ''")
    planos = [u for u in usuarios if not u['password'].startswith(PREFIJOS_HASH)]
    print(f"Usuarios con contraseña: {len(usuarios)} | en texto plano: {len(planos)}")
    for u in planos:
        print(f"  - {u['usuario_sistema']} (id {u['id']})")
    if not aplicar:
        print("\nModo prueba: no se cambió nada. Ejecuta con --aplicar para convertirlas.")
        return
    with db_tx() as conn:
        cur = conn.cursor()
        for u in planos:
            cur.execute("UPDATE usuarios SET password = %s WHERE id = %s AND password = %s",
                        (generate_password_hash(u['password']), u['id'], u['password']))
    print(f"\n✅ {len(planos)} contraseñas convertidas a hash.")


if __name__ == '__main__':
    main()
