from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from modulos.database import get_db, get_cupo_hoy, registrar_auditoria, ESTADOS, BADGES
from datetime import datetime, date

pedidos_bp = Blueprint("pedidos", __name__)


def login_requerido(f):
    from functools import wraps
    @wraps(f)
    def decorado(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesion para continuar", "error")
            return redirect(url_for("usuarios.login"))
        return f(*args, **kwargs)
    return decorado


@pedidos_bp.route("/confirmar-pedido", methods=["POST"])
@login_requerido
def confirmar():
    carrito = session.get("carrito", {})
    if not carrito:
        flash("Tu carrito esta vacio", "error")
        return redirect(url_for("catalogo.ver_carrito"))

    total_qty = sum(carrito.values())
    if total_qty < 6:
        flash("El minimo de unidades para pedido es 6", "error")
        return redirect(url_for("catalogo.ver_carrito"))

    cupo = get_cupo_hoy()
    disponibles = cupo["cupo_maximo"] - cupo["unidades_reservadas"]
    if total_qty > disponibles:
        flash(f"Solo quedan {disponibles} unidades disponibles hoy", "error")
        return redirect(url_for("catalogo.ver_carrito"))

    db = get_db()
    total = 0
    for pid, qty in carrito.items():
        p = db.execute("SELECT precio FROM productos WHERE id = ?", (pid,)).fetchone()
        if p:
            total += p["precio"] * qty

    codigo = f"VD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    fecha_entrega = request.form.get("fecha_entrega", "")
    notas = request.form.get("notas", "")

    db.execute(
        "INSERT INTO pedidos (codigo, id_usuario, total, fecha_entrega, notas) VALUES (?, ?, ?, ?, ?)",
        (codigo, session["user_id"], total, fecha_entrega, notas)
    )
    id_pedido = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for pid, qty in carrito.items():
        p = db.execute("SELECT precio FROM productos WHERE id = ?", (pid,)).fetchone()
        if p:
            db.execute(
                "INSERT INTO detalle_pedido (id_pedido, id_producto, cantidad, precio_unitario) VALUES (?, ?, ?, ?)",
                (id_pedido, int(pid), qty, p["precio"])
            )

    db.execute(
        "UPDATE cupo_diario SET unidades_reservadas = unidades_reservadas + ? WHERE fecha = ?",
        (total_qty, date.today().isoformat())
    )
    db.commit()

    registrar_auditoria("crear", f"Pedido {codigo} creado por {session.get('correo')}")
    session.pop("carrito", None)
    flash(f"Pedido {codigo} confirmado con exito!", "success")
    return redirect(url_for("pedidos.mis_pedidos"))


@pedidos_bp.route("/mis-pedidos")
@login_requerido
def mis_pedidos():
    db = get_db()
    pedidos = db.execute("""
        SELECT p.*, GROUP_CONCAT(pr.nombre || ' x' || dp.cantidad, ' | ') AS items_str
        FROM pedidos p
        LEFT JOIN detalle_pedido dp ON dp.id_pedido = p.id
        LEFT JOIN productos pr ON pr.id = dp.id_producto
        WHERE p.id_usuario = ?
        GROUP BY p.id
        ORDER BY p.fecha DESC
    """, (session["user_id"],)).fetchall()
    pasos = ["Pendiente", "En preparacion", "Listo para entrega", "Entregado"]
    return render_template("mis_pedidos.html", pedidos=pedidos, pasos=pasos, BADGES=BADGES)
