"""Routes for prompt-based draft generation."""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.models import DraftResponse, PromptRequest, SourceRecommendationResponse
from core.generator import GeneratorNotConfiguredError, generate_draft
from core.source_recommender import recommend_sources

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the ProtoCheck workspace scaffold."""
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request=request, name="index.html")


@router.post("/api/generate", response_model=DraftResponse)
async def generate(request: PromptRequest) -> DraftResponse:
    """Generate a draft through the configured text provider."""
    try:
        return DraftResponse(answer=generate_draft(request.prompt))
    except GeneratorNotConfiguredError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post("/api/sources/recommend", response_model=SourceRecommendationResponse)
async def source_recommendations(request: PromptRequest) -> SourceRecommendationResponse:
    """Recommend discoverable sources; this endpoint never creates evidence."""
    return recommend_sources(request.prompt)


@router.post("/api/source-recommendations", response_model=SourceRecommendationResponse, include_in_schema=False)
async def legacy_source_recommendations(request: PromptRequest) -> SourceRecommendationResponse:
    """Compatibility alias for the initial Stage 3 frontend endpoint."""
    return recommend_sources(request.prompt)
