from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from modulos.database import get_db, get_cupo_hoy, registrar_auditoria

catalogo_bp = Blueprint("catalogo", __name__)


def login_requerido(f):
    from functools import wraps
    @wraps(f)
    def decorado(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesion para continuar", "error")
            return redirect(url_for("usuarios.login"))
        return f(*args, **kwargs)
    return decorado


@catalogo_bp.route("/")
def index():
    db = get_db()
    categoria = request.args.get("cat", "todos")
    if categoria == "todos":
        productos = db.execute("SELECT * FROM productos ORDER BY disponible DESC, id").fetchall()
    else:
        productos = db.execute(
            "SELECT * FROM productos WHERE categoria = ? ORDER BY disponible DESC, id",
            (categoria,)
        ).fetchall()
    cupo = get_cupo_hoy()
    return render_template("catalogo.html", productos=productos, cupo=cupo, categoria=categoria)


@catalogo_bp.route("/carrito/agregar/<int:pid>", methods=["POST"])
@login_requerido
def agregar(pid):
    cupo = get_cupo_hoy()
    disponibles = cupo["cupo_maximo"] - cupo["unidades_reservadas"]
    carrito = session.get("carrito", {})
    if sum(carrito.values()) >= disponibles:
        flash("No hay mas cupo disponible para hoy", "error")
        return redirect(url_for("catalogo.index"))
    db = get_db()
    p = db.execute("SELECT * FROM productos WHERE id = ? AND disponible = 1", (pid,)).fetchone()
    if not p:
        flash("Producto no disponible", "error")
        return redirect(url_for("catalogo.index"))
    carrito[str(pid)] = carrito.get(str(pid), 0) + 1
    session["carrito"] = carrito
    flash(f"{p['nombre']} agregado al carrito", "success")
    return redirect(url_for("catalogo.index"))


@catalogo_bp.route("/carrito")
@login_requerido
def ver_carrito():
    carrito = session.get("carrito", {})
    db = get_db()
    items = []
    total = 0
    for pid, qty in carrito.items():
        p = db.execute("SELECT * FROM productos WHERE id = ?", (pid,)).fetchone()
        if p:
            sub = p["precio"] * qty
            items.append({"producto": dict(p), "qty": qty, "subtotal": sub})
            total += sub
    total_qty = sum(carrito.values())
    return render_template("carrito.html", items=items, total=total, total_qty=total_qty)


@catalogo_bp.route("/carrito/cambiar/<int:pid>/<accion>", methods=["POST"])
@login_requerido
def cambiar_qty(pid, accion):
    carrito = session.get("carrito", {})
    key = str(pid)
    if accion == "mas":
        carrito[key] = carrito.get(key, 0) + 1
    elif accion == "menos":
        carrito[key] = carrito.get(key, 0) - 1
        if carrito[key] <= 0:
            carrito.pop(key, None)
    elif accion == "eliminar":
        carrito.pop(key, None)
    session["carrito"] = carrito
    return redirect(url_for("catalogo.ver_carrito"))
