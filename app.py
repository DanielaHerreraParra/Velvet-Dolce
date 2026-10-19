from flask import Flask
from modulos.database import init_db, close_db
from modulos.usuarios import usuarios_bp
from modulos.catalogo import catalogo_bp
from modulos.pedidos import pedidos_bp
from modulos.admin import admin_bp

app = Flask(__name__)
app.secret_key = "velvetdolce2026"
app.config["UPLOAD_FOLDER"] = "static/img/productos"
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

app.register_blueprint(usuarios_bp)
app.register_blueprint(catalogo_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(admin_bp)

app.teardown_appcontext(close_db)

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
