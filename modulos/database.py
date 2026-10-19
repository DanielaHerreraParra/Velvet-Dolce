import sqlite3
import hashlib
from datetime import date
from flask import g, request, session

DB = "velvetdolce.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()


def registrar_auditoria(tipo, accion):
    ip = request.remote_addr or "127.0.0.1"
    usuario = session.get("correo", "anonimo")
    db = get_db()
    db.execute(
        "INSERT INTO auditoria (tipo, accion, usuario, ip) VALUES (?, ?, ?, ?)",
        (tipo, accion, usuario, ip)
    )
    db.commit()


def get_cupo_hoy():
    hoy = date.today().isoformat()
    db = get_db()
    fila = db.execute("SELECT * FROM cupo_diario WHERE fecha = ?", (hoy,)).fetchone()
    if not fila:
        db.execute(
            "INSERT INTO cupo_diario (fecha, cupo_maximo, unidades_reservadas) VALUES (?, 180, 0)",
            (hoy,)
        )
        db.commit()
        fila = db.execute("SELECT * FROM cupo_diario WHERE fecha = ?", (hoy,)).fetchone()
    return dict(fila)


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_completo TEXT    NOT NULL,
            correo          TEXT    UNIQUE NOT NULL,
            contrasena      TEXT    NOT NULL,
            rol             TEXT    DEFAULT 'cliente',
            activo          INTEGER DEFAULT 1,
            fecha_registro  TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS productos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT    NOT NULL,
            descripcion TEXT,
            precio      INTEGER NOT NULL,
            categoria   TEXT,
            imagen      TEXT    DEFAULT 'placeholder.png',
            disponible  INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo        TEXT    UNIQUE NOT NULL,
            id_usuario    INTEGER NOT NULL,
            total         INTEGER NOT NULL,
            estado        TEXT    DEFAULT 'Pendiente',
            fecha         TEXT    DEFAULT CURRENT_TIMESTAMP,
            fecha_entrega TEXT,
            notas         TEXT
        );

        CREATE TABLE IF NOT EXISTS detalle_pedido (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pedido       INTEGER NOT NULL,
            id_producto     INTEGER NOT NULL,
            cantidad        INTEGER NOT NULL,
            precio_unitario INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cupo_diario (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha               TEXT    UNIQUE NOT NULL,
            cupo_maximo         INTEGER DEFAULT 180,
            unidades_reservadas INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS auditoria (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo    TEXT NOT NULL,
            accion  TEXT NOT NULL,
            usuario TEXT NOT NULL,
            ip      TEXT,
            fecha   TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Usuarios iniciales
    if not c.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        c.execute(
            "INSERT INTO usuarios (nombre_completo, correo, contrasena, rol) VALUES (?, ?, ?, ?)",
            ("Administrador", "admin@velvetdolce.com", hash_pwd("admin1234"), "administrador")
        )
        c.execute(
            "INSERT INTO usuarios (nombre_completo, correo, contrasena, rol) VALUES (?, ?, ?, ?)",
            ("Ana Martinez", "cliente@velvetdolce.com", hash_pwd("cliente1234"), "cliente")
        )

    # Productos iniciales
    if not c.execute("SELECT 1 FROM productos LIMIT 1").fetchone():
        productos = [
            ("Red Velvet Clasico", "Cupcake estrella con frosting de queso crema", 12000, "clasico", "placeholder.png", 1),
            ("Red Velvet Fresa",   "Con coulis de fresa natural",                  13500, "especiales", "placeholder.png", 1),
            ("Red Velvet Choco",   "Doble relleno de chocolate belga",             14000, "especiales", "placeholder.png", 1),
            ("Red Velvet Mini",    "Version mini perfecta para degustar",           7000, "clasico",    "placeholder.png", 1),
        ]
        c.executemany(
            "INSERT INTO productos (nombre, descripcion, precio, categoria, imagen, disponible) VALUES (?, ?, ?, ?, ?, ?)",
            productos
        )

    # Cupo inicial
    hoy = date.today().isoformat()
    if not c.execute("SELECT 1 FROM cupo_diario LIMIT 1").fetchone():
        c.execute(
            "INSERT INTO cupo_diario (fecha, cupo_maximo, unidades_reservadas) VALUES (?, 180, 0)",
            (hoy,)
        )

    conn.commit()
    conn.close()


ESTADOS = ["Pendiente", "En preparacion", "Listo para entrega", "Entregado", "Cancelado"]

BADGES = {
    "Pendiente":          "badge-pending",
    "En preparacion":     "badge-prep",
    "Listo para entrega": "badge-ready",
    "Entregado":          "badge-delivered",
    "Cancelado":          "badge-cancelled",
}
