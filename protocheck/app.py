"""Application entry point for the ProtoCheck local development scaffold."""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routes.chat import router as chat_router
from routes.claims import router as claims_router
from routes.evidence import router as evidence_router
from routes.verification import router as verification_router

load_dotenv()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="ProtoCheck", version="0.1.0")
    application.mount("/static", StaticFiles(directory="static"), name="static")
    application.state.templates = Jinja2Templates(directory="templates")
    application.include_router(chat_router)
    application.include_router(claims_router)
    application.include_router(evidence_router)
    application.include_router(verification_router)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)