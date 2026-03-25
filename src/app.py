"""Entry point — creates the FastAPI app via factory."""
from src.web import create_app

app = create_app()
