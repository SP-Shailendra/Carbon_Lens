import secrets
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response
from fastapi.security import APIKeyHeader

from .agent import AnalysisError, analyze_usage
from .config import Settings
from .data.export import report_csv
from .emissions.factors import EMISSION_FACTORS, REGISTRY_INFO, USAGE_PROFILES, load_factor_file
from .models.schemas import AnalysisReport, FunnelEvent, RecommendationFeedback, ReportListItem
from .recommendations.llm_explainer import explain_hotspots
from .storage import ReportStore


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or Settings()
    store = ReportStore(config.database_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        store.initialize()
        if config.factors_path:
            load_factor_file(config.factors_path)
        yield

    application = FastAPI(
        title="CarbonLens agent API",
        version="0.1.0",
        lifespan=lifespan,
        description="Validate cloud usage, calculate traceable estimates, and record human decisions. No cloud execution.",
    )
    application.state.store = store
    key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def authorize(key: Annotated[str | None, Depends(key_header)]):
        if config.api_key and (key is None or not secrets.compare_digest(key, config.api_key)):
            raise HTTPException(status_code=401, detail="A valid X-API-Key header is required.")

    protected = [Depends(authorize)]

    @application.get("/", include_in_schema=False)
    def index():
        return RedirectResponse("/docs")

    @application.get("/health", tags=["Operations"])
    def health():
        return {"status": "ok", "service": "carbonlens", "version": "0.1.0"}

    @application.get("/api/v1/config", dependencies=protected, tags=["Operations"])
    def capabilities():
        return {
            "providers": ["aws", "azure", "gcp"],
            "max_upload_mb": config.max_upload_mb,
            "max_rows": 50_000,
            "max_recommendations": 3,
            "configured_factors": len(EMISSION_FACTORS),
            "ai_available": config.llm_provider == "openai" and bool(config.llm_api_key),
            "executes_cloud_changes": False,
            "sample_profiles": ["mixed", "aws-electricity-2023"],
            "methodology_version": "2",
            "registry_version": REGISTRY_INFO.get("registry_version"),
            "estimate_methods": ["provider_reported", "estimated_usage", "not_estimated"],
        }

    @application.get("/api/v1/factors", dependencies=protected, tags=["Methodology"])
    def factors():
        return [{"key": key, **asdict(factor)} for key, factor in EMISSION_FACTORS.items()]

    @application.get("/api/v1/registry", dependencies=protected, tags=["Methodology"])
    def registry():
        return {
            **REGISTRY_INFO,
            "factors": factors(),
            "usage_profiles": [
                profile.model_dump(mode="json") for profile in USAGE_PROFILES.values()
            ],
        }

    @application.post("/api/v1/events", dependencies=protected, tags=["Operations"])
    def event(payload: FunnelEvent):
        if payload.name == "onboarding_started" and payload.report_id is not None:
            raise HTTPException(
                status_code=422, detail="Onboarding events cannot include report data."
            )
        if payload.name == "report_viewed" and (
            not payload.report_id or store.get(payload.report_id) is None
        ):
            raise HTTPException(status_code=404, detail="Report not found.")
        store.event(payload.report_id or "", payload.name)
        return {"recorded": True}

    def build_report(content: bytes, top_n: int, use_ai: bool, data_origin: str = "uploaded"):
        analysis_id = str(uuid4())
        store.event(analysis_id, "upload_submitted")
        try:
            report = analyze_usage(content, top_n)
        except AnalysisError as error:
            raise HTTPException(status_code=422, detail={"errors": error.errors}) from error
        report["id"] = analysis_id
        report["data_origin"] = data_origin
        if data_origin == "synthetic_sample":
            report["warnings"].insert(
                0,
                "Synthetic sample activity, not measured customer usage or evidence of real-world impact.",
            )
        if use_ai and report["recommendations"]:
            try:
                labels = explain_hotspots(report["recommendations"], config)
                by_id = {label["id"]: label["action"] for label in labels}
                for item in report["recommendations"]:
                    item["ai_action"] = by_id[item["id"]]
                report["explanation_mode"] = "ai_assisted"
            except Exception:
                report["warnings"].append(
                    "AI labeling was unavailable or invalid; deterministic explanations were retained."
                )
        elif use_ai:
            report["warnings"].append(
                "AI labeling was skipped because there are no supported estimated hotspots."
            )
        validated = AnalysisReport.model_validate(report).model_dump()
        store.save(validated)
        return validated

    @application.post(
        "/api/v1/analyses",
        response_model=AnalysisReport,
        status_code=201,
        dependencies=protected,
        tags=["Agent"],
    )
    async def analyze(
        file: Annotated[UploadFile, File(description="Normalized UTF-8 cloud usage CSV")],
        top_n: Annotated[int, Query(ge=1, le=3)] = 3,
        use_ai: bool = False,
    ):
        try:
            if not (file.filename or "").lower().endswith(".csv"):
                raise HTTPException(status_code=415, detail="Upload a .csv file.")
            content = await file.read(config.max_upload_mb * 1024 * 1024 + 1)
            if len(content) > config.max_upload_mb * 1024 * 1024:
                raise HTTPException(
                    status_code=413, detail=f"Upload exceeds {config.max_upload_mb} MB."
                )
        finally:
            await file.close()
        return await run_in_threadpool(build_report, content, top_n, use_ai)

    @application.post(
        "/api/v1/analyses/sample",
        response_model=AnalysisReport,
        status_code=201,
        dependencies=protected,
        tags=["Agent"],
    )
    def analyze_sample(
        top_n: Annotated[int, Query(ge=1, le=3)] = 3,
        use_ai: bool = False,
        profile: Literal["mixed", "aws-electricity-2023"] = "mixed",
    ):
        filename = (
            "sample_aws_electricity_2023.csv"
            if profile == "aws-electricity-2023"
            else "sample_cloud_usage.csv"
        )
        sample = Path(__file__).resolve().parents[2] / "data" / filename
        return build_report(sample.read_bytes(), top_n, use_ai, "synthetic_sample")

    @application.get(
        "/api/v1/analyses",
        response_model=list[ReportListItem],
        dependencies=protected,
        tags=["Reports"],
    )
    def list_reports(limit: Annotated[int, Query(ge=1, le=100)] = 20):
        reports = store.list_reports(limit)
        for item in reports:
            if item.get("methodology_version") != "2":
                item["summary"] = {
                    **item["summary"],
                    "estimated_kg_co2e": None,
                    "method": "not_estimated",
                    "low_kg_co2e": None,
                    "central_kg_co2e": None,
                    "high_kg_co2e": None,
                    "totals_by_method": [],
                    "range_assumption": "Legacy point estimate; reanalyze original CSV for methodology v2.",
                }
        return reports

    @application.get(
        "/api/v1/analyses/{report_id}",
        response_model=AnalysisReport,
        dependencies=protected,
        tags=["Reports"],
    )
    def get_report(report_id: UUID):
        report = store.get(str(report_id))
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        if report.get("methodology_version") != "2":
            raise HTTPException(
                status_code=409,
                detail="Saved report uses an older point-estimate methodology. Reanalyze the original CSV for v2 ranges; stored data is unchanged.",
            )
        return report

    @application.get("/api/v1/analyses/{report_id}/csv", dependencies=protected, tags=["Reports"])
    def export_csv(report_id: UUID):
        report = get_report(report_id)
        return Response(
            report_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="carbonlens-{report_id}.csv"'},
        )

    @application.post(
        "/api/v1/analyses/{report_id}/decisions",
        response_model=AnalysisReport,
        dependencies=protected,
        tags=["Human review"],
    )
    def decision(report_id: UUID, feedback: RecommendationFeedback):
        get_report(report_id)
        report = store.decide(str(report_id), feedback.recommendation_id, feedback.decision)
        if report is None:
            raise HTTPException(status_code=404, detail="Report or recommendation not found.")
        return report

    return application


app = create_app()
