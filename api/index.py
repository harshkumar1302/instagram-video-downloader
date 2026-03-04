from backend.server import app

# Vercel requires the variable name "app"
# so we expose the Flask instance
app = app