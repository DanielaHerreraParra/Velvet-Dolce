from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from modulos.database import get_db, hash_pwd, registrar_auditoria

usuarios_bp = Blueprint("usuarios", __name__)


@usuarios_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form["correo"].strip()
        pwd = hash_pwd(request.form["contrasena"])
        db = get_db()
        user = db.execute(
            "SELECT * FROM usuarios WHERE correo = ? AND contrasena = ? AND activo = 1",
            (correo, pwd)
        ).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["nombre"]  = user["nombre_completo"]
            session["correo"]  = user["correo"]
            session["rol"]     = user["rol"]
            registrar_auditoria("acceso", f"Login: {correo}")
            flash(f"Bienvenido, {user['nombre_completo']}!", "success")
            if user["rol"] == "administrador":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("catalogo.index"))
        flash("Correo o contrasena incorrectos", "error")
    return render_template("login.html")


@usuarios_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        correo = request.form["correo"].strip()
        pwd    = request.form["contrasena"]
        pwd2   = request.form["contrasena2"]
        if len(pwd) < 8:
            flash("La contrasena debe tener minimo 8 caracteres", "error")
        elif pwd != pwd2:
            flash("Las contrasenas no coinciden", "error")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO usuarios (nombre_completo, correo, contrasena) VALUES (?, ?, ?)",
                    (nombre, correo, hash_pwd(pwd))
                )
                db.commit()
                user = db.execute("SELECT * FROM usuarios WHERE correo = ?", (correo,)).fetchone()
                session["user_id"] = user["id"]
                session["nombre"]  = user["nombre_completo"]
                session["correo"]  = user["correo"]
                session["rol"]     = user["rol"]
                registrar_auditoria("crear", f"Registro nuevo usuario: {correo}")
                flash(f"Cuenta creada. Bienvenido, {nombre}!", "success")
                return redirect(url_for("catalogo.index"))
            except Exception:
                flash("Este correo ya esta registrado", "error")
    return render_template("registro.html")


@usuarios_bp.route("/logout")
def logout():
    registrar_auditoria("acceso", f"Logout: {session.get('correo', '')}")
    session.clear()
    flash("Sesion cerrada", "info")
    return redirect(url_for("catalogo.index"))
