from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, send_file
from io import BytesIO
from openpyxl import Workbook
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from modulos.database import get_db, get_cupo_hoy, registrar_auditoria, ESTADOS, BADGES
from datetime import date
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

EXTENSIONES = {"png", "jpg", "jpeg"}


def admin_requerido(f):
    from functools import wraps
    @wraps(f)
    def decorado(*args, **kwargs):
        if session.get("rol") != "administrador":
            flash("Acceso solo para administradores", "error")
            return redirect(url_for("catalogo.index"))
        return f(*args, **kwargs)
    return decorado


def guardar_imagen(archivo):
    if not archivo or archivo.filename == "":
        return None
    ext = archivo.filename.rsplit(".", 1)[-1].lower()
    if ext not in EXTENSIONES:
        return None
    nombre = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}.{ext}"
    carpeta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(carpeta, exist_ok=True)
    archivo.save(os.path.join(carpeta, nombre))
    return nombre


def borrar_imagen(nombre):
    if nombre and nombre != "placeholder.png":
        ruta = os.path.join(current_app.config["UPLOAD_FOLDER"], nombre)
        if os.path.exists(ruta):
            os.remove(ruta)


@admin_bp.route("/")
@admin_requerido
def dashboard():
    db = get_db()
    hoy = date.today().isoformat()
    pedidos_hoy = db.execute(
        "SELECT COUNT(*) FROM pedidos WHERE fecha LIKE ?", (hoy + "%",)
    ).fetchone()[0]
    ventas_hoy = db.execute(
        "SELECT COALESCE(SUM(total), 0) FROM pedidos WHERE fecha LIKE ? AND estado != 'Cancelado'",
        (hoy + "%",)
    ).fetchone()[0]
    clientes = db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'cliente'").fetchone()[0]
    cupo = get_cupo_hoy()
    ultimos = db.execute("""
        SELECT p.codigo, u.nombre_completo, p.total, p.estado
        FROM pedidos p JOIN usuarios u ON u.id = p.id_usuario
        ORDER BY p.fecha DESC LIMIT 5
    """).fetchall()
    return render_template("admin/dashboard.html",
        pedidos_hoy=pedidos_hoy, ventas_hoy=ventas_hoy,
        clientes=clientes, cupo=cupo, ultimos=ultimos, BADGES=BADGES)


@admin_bp.route("/pedidos")
@admin_requerido
def pedidos():
    db = get_db()
    buscar = request.args.get("q", "")
    estado = request.args.get("estado", "")
    sql = """SELECT p.*, u.nombre_completo FROM pedidos p
             JOIN usuarios u ON u.id = p.id_usuario WHERE 1=1"""
    params = []
    if buscar:
        sql += " AND (u.nombre_completo LIKE ? OR p.codigo LIKE ?)"
        params += [f"%{buscar}%", f"%{buscar}%"]
    if estado:
        sql += " AND p.estado = ?"
        params.append(estado)
    sql += " ORDER BY p.fecha DESC"
    lista = db.execute(sql, params).fetchall()
    return render_template("admin/pedidos.html",
        pedidos=lista, ESTADOS=ESTADOS, BADGES=BADGES, buscar=buscar, estado=estado)

@admin_bp.route("/pedidos/<int:pid>")
@admin_requerido
def detalle_pedido(pid):
    db = get_db()

    # Lista de pedidos (igual que la vista principal)
    lista = db.execute("""
        SELECT p.*, u.nombre_completo
        FROM pedidos p
        JOIN usuarios u ON u.id = p.id_usuario
        ORDER BY p.fecha DESC
    """).fetchall()

    # Información del pedido seleccionado
    pedido = db.execute("""
        SELECT p.*, u.nombre_completo, u.correo
        FROM pedidos p
        JOIN usuarios u ON u.id = p.id_usuario
        WHERE p.id = ?
    """, (pid,)).fetchone()

    # Productos del pedido
    detalle = db.execute("""
        SELECT
            pr.nombre,
            pr.imagen,
            dp.cantidad,
            dp.precio_unitario,
            dp.cantidad * dp.precio_unitario AS subtotal
        FROM detalle_pedido dp
        JOIN productos pr
            ON pr.id = dp.id_producto
        WHERE dp.id_pedido = ?
    """, (pid,)).fetchall()

    return render_template(
        "admin/pedidos.html",
        pedidos=lista,
        pedido=pedido,
        detalle=detalle,
        ESTADOS=ESTADOS,
        BADGES=BADGES,
        buscar="",
        estado=""
    )

@admin_bp.route("/pedidos/estado/<int:pid>", methods=["POST"])
@admin_requerido
def cambiar_estado(pid):
    nuevo = request.form["estado"]
    db = get_db()
    anterior = db.execute("SELECT codigo, estado FROM pedidos WHERE id = ?", (pid,)).fetchone()
    db.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (nuevo, pid))
    db.commit()
    registrar_auditoria("editar", f"Pedido {anterior['codigo']}: '{anterior['estado']}' -> '{nuevo}'")
    flash(f"Estado actualizado a '{nuevo}'", "success")
    return redirect(url_for("admin.pedidos"))


@admin_bp.route("/productos")
@admin_requerido
def productos():
    db = get_db()
    lista = db.execute("SELECT * FROM productos ORDER BY id").fetchall()
    return render_template("admin/productos.html", productos=lista)


@admin_bp.route("/productos/nuevo", methods=["POST"])
@admin_requerido
def nuevo_producto():
    nombre = request.form["nombre"].strip()
    precio = int(request.form["precio"])
    cat    = request.form["categoria"]
    desc   = request.form.get("descripcion", "").strip()
    imagen = guardar_imagen(request.files.get("imagen")) or "placeholder.png"
    db = get_db()
    db.execute(
        "INSERT INTO productos (nombre, descripcion, precio, categoria, imagen) VALUES (?, ?, ?, ?, ?)",
        (nombre, desc, precio, cat, imagen)
    )
    db.commit()
    registrar_auditoria("crear", f"Producto '{nombre}' creado")
    flash(f"Producto '{nombre}' agregado", "success")
    return redirect(url_for("admin.productos"))


@admin_bp.route("/productos/editar/<int:pid>", methods=["POST"])
@admin_requerido
def editar_producto(pid):
    db = get_db()
    p  = db.execute("SELECT * FROM productos WHERE id = ?", (pid,)).fetchone()
    nombre = request.form["nombre"].strip()
    precio = int(request.form["precio"])
    cat    = request.form["categoria"]
    desc   = request.form.get("descripcion", "").strip()
    nueva  = guardar_imagen(request.files.get("imagen"))
    if nueva:
        borrar_imagen(p["imagen"])
        imagen = nueva
    else:
        imagen = p["imagen"]
    db.execute(
        "UPDATE productos SET nombre=?, descripcion=?, precio=?, categoria=?, imagen=? WHERE id=?",
        (nombre, desc, precio, cat, imagen, pid)
    )
    db.commit()
    registrar_auditoria("editar", f"Producto '{nombre}' editado")
    flash(f"Producto '{nombre}' actualizado", "success")
    return redirect(url_for("admin.productos"))


@admin_bp.route("/productos/toggle/<int:pid>", methods=["POST"])
@admin_requerido
def toggle_producto(pid):
    db = get_db()
    p  = db.execute("SELECT * FROM productos WHERE id = ?", (pid,)).fetchone()
    nuevo = 0 if p["disponible"] else 1
    db.execute("UPDATE productos SET disponible = ? WHERE id = ?", (nuevo, pid))
    db.commit()
    estado = "activado" if nuevo else "desactivado"
    registrar_auditoria("editar", f"Producto '{p['nombre']}' {estado}")
    flash(f"Producto {estado}", "success")
    return redirect(url_for("admin.productos"))


@admin_bp.route("/productos/eliminar/<int:pid>", methods=["POST"])
@admin_requerido
def eliminar_producto(pid):
    db = get_db()
    p  = db.execute("SELECT * FROM productos WHERE id = ?", (pid,)).fetchone()
    borrar_imagen(p["imagen"])
    db.execute("DELETE FROM productos WHERE id = ?", (pid,))
    db.commit()
    registrar_auditoria("eliminar", f"Producto '{p['nombre']}' eliminado")
    flash("Producto eliminado", "info")
    return redirect(url_for("admin.productos"))


@admin_bp.route("/cupo", methods=["GET", "POST"])
@admin_requerido
def cupo():
    if request.method == "POST":
        fecha  = request.form["fecha"]
        maximo = int(request.form["cupo_maximo"])
        if maximo < 150 or maximo > 200:
            flash("El cupo debe estar entre 150 y 200", "error")
        else:
            db = get_db()
            db.execute("""
                INSERT INTO cupo_diario (fecha, cupo_maximo, unidades_reservadas) VALUES (?, ?, 0)
                ON CONFLICT(fecha) DO UPDATE SET cupo_maximo = excluded.cupo_maximo
            """, (fecha, maximo))
            db.commit()
            registrar_auditoria("editar", f"Cupo {fecha} ajustado a {maximo}")
            flash(f"Cupo del {fecha} actualizado a {maximo}", "success")
        return redirect(url_for("admin.cupo"))
    db = get_db()
    historial = db.execute("SELECT * FROM cupo_diario ORDER BY fecha DESC LIMIT 30").fetchall()
    return render_template("admin/cupo.html", cupo_hoy=get_cupo_hoy(), historial=historial)


@admin_bp.route("/reportes")
@admin_requerido
def reportes():
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    accion = request.args.get("accion", "ver")
    datos = None
    if desde and hasta:
        db = get_db()
        pedidos = db.execute("""
            SELECT p.*, u.nombre_completo FROM pedidos p
            JOIN usuarios u ON u.id = p.id_usuario
            WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado'
            ORDER BY p.fecha DESC
        """, (desde, hasta + " 23:59:59")).fetchall()

        brutos = sum(p["total"] for p in pedidos)
        unidades = db.execute("""
            SELECT COALESCE(SUM(dp.cantidad), 0) FROM detalle_pedido dp
            JOIN pedidos p ON p.id = dp.id_pedido
            WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado'
        """, (desde, hasta + " 23:59:59")).fetchone()[0]

        top = db.execute("""
            SELECT pr.nombre, pr.imagen, SUM(dp.cantidad) AS total_uds
            FROM detalle_pedido dp
            JOIN pedidos p ON p.id = dp.id_pedido
            JOIN productos pr ON pr.id = dp.id_producto
            WHERE p.fecha BETWEEN ? AND ? AND p.estado != 'Cancelado'
            GROUP BY dp.id_producto ORDER BY total_uds DESC LIMIT 5
        """, (desde, hasta + " 23:59:59")).fetchall()

        por_estado = db.execute("""
            SELECT estado, COUNT(*) AS cnt FROM pedidos
            WHERE fecha BETWEEN ? AND ? GROUP BY estado
        """, (desde, hasta + " 23:59:59")).fetchall()

        datos = dict(
            total=len(pedidos), brutos=brutos,
            netos=int(brutos * 0.88), unidades=unidades,
            top=top, max_uds=top[0]["total_uds"] if top else 1,
            por_estado=por_estado
        )
        
        if accion == "excel":
            archivo = BytesIO()

            wb = Workbook()
            ws = wb.active
            ws.title = "Reporte"

            ws.append(["Total pedidos", datos["total"]])
            ws.append(["Ingresos brutos", datos["brutos"]])
            ws.append(["Ingresos netos", datos["netos"]])
            ws.append(["Unidades vendidas", datos["unidades"]])

            ws.append([])
            ws.append(["Productos más vendidos"])

            ws.append(["Producto", "Unidades"])

            for producto in top:
                ws.append([producto["nombre"], producto["total_uds"]])

            wb.save(archivo)
            archivo.seek(0)

            return send_file(
                archivo,
                download_name="ReporteVentas.xlsx",
                as_attachment=True,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        if accion == "pdf":
            archivo = BytesIO()

            pdf = SimpleDocTemplate(archivo)

            elementos = []

            tabla = Table([
                ["Concepto", "Valor"],
                ["Total pedidos", datos["total"]],
                ["Ingresos brutos", f"${datos['brutos']}"],
                ["Ingresos netos", f"${datos['netos']}"],
                ["Unidades vendidas", datos["unidades"]],
            ])

            tabla.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),colors.pink),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("GRID",(0,0),(-1,-1),1,colors.black),
                ("BOTTOMPADDING",(0,0),(-1,0),10)
            ]))

            elementos.append(tabla)

            pdf.build(elementos)

            archivo.seek(0)

            return send_file(
                archivo,
                download_name="ReporteVentas.pdf",
                as_attachment=True,
                mimetype="application/pdf"
            )
    return render_template("admin/reportes.html", datos=datos, desde=desde, hasta=hasta)


@admin_bp.route("/auditoria")
@admin_requerido
def auditoria():
    tipo    = request.args.get("tipo", "")
    usuario = request.args.get("usuario", "")
    db = get_db()
    sql = "SELECT * FROM auditoria WHERE 1=1"
    params = []
    if tipo:
        sql += " AND tipo = ?"; params.append(tipo)
    if usuario:
        sql += " AND usuario LIKE ?"; params.append(f"%{usuario}%")
    sql += " ORDER BY fecha DESC LIMIT 200"
    logs = db.execute(sql, params).fetchall()
    return render_template("admin/auditoria.html", logs=logs, tipo=tipo, usuario=usuario)
