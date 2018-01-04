from core_server import app
from werkzeug.contrib.fixers import ProxyFix

if __name__ == "__main__":
    # For proper https forwarding? (see https://github.com/noirbizarre/flask-restplus/issues/54)
    app.wsgi_app = ProxyFix(app.wsgi_app)
    app.run()
