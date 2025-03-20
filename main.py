from app import app
from routes import auth, servers, domains, domain_groups, proxy
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Register blueprints
app.register_blueprint(auth.bp)
app.register_blueprint(servers.bp)
app.register_blueprint(domains.bp)
app.register_blueprint(domain_groups.bp)
app.register_blueprint(proxy.bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
