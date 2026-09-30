"""Full OpenAPI contract parity test validating FastAPI schema against spec openapi.yaml."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml  # type: ignore[import-untyped]

from src.main import create_app

SPEC_FILE = (
    Path(__file__).parents[2]
    / "specs"
    / "001-work-management-platform"
    / "contracts"
    / "openapi.yaml"
)


@pytest.fixture(scope="module")
def expected_spec() -> dict[str, Any]:
    """Load the approved OpenAPI 3.1 contract specification."""
    with open(SPEC_FILE, encoding="utf-8") as f:
        spec_data = yaml.safe_load(f)
    return spec_data  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def generated_schema() -> dict[str, Any]:
    """Generate OpenAPI schema directly from the FastAPI application."""
    application = create_app()
    return application.openapi()


def test_openapi_version_and_metadata(generated_schema: dict[str, Any]) -> None:
    """Verify OpenAPI version is 3.1.x and metadata is configured."""
    assert generated_schema["openapi"].startswith("3.1.")
    assert "info" in generated_schema
    assert "title" in generated_schema["info"]
    assert "version" in generated_schema["info"]


def test_all_contract_paths_and_methods_exist(
    expected_spec: dict[str, Any],
    generated_schema: dict[str, Any],
) -> None:
    """Verify every path and HTTP operation in the contract exists in the generated schema."""
    expected_paths = expected_spec.get("paths", {})
    generated_paths = generated_schema.get("paths", {})

    missing_endpoints: list[str] = []

    for path, path_item in expected_paths.items():
        # In the contract, servers has url: /api/v1 except operational /health and /ready
        actual_path = f"/api/v1{path}" if path not in ["/health", "/ready"] else path

        if actual_path not in generated_paths:
            missing_endpoints.append(f"Path missing: {actual_path}")
            continue

        gen_item = generated_paths[actual_path]
        for method in path_item:
            if method.lower() in ["get", "post", "put", "patch", "delete"]:
                if method.lower() not in gen_item:
                    missing_endpoints.append(f"Method missing: {method.upper()} {actual_path}")

    assert not missing_endpoints, f"OpenAPI contract deviations detected: {missing_endpoints}"


@pytest.mark.asyncio
async def test_openapi_endpoint_accessibility(async_client: httpx.AsyncClient) -> None:
    """Verify GET /openapi.json returns HTTP 200 with complete specification."""
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "components" in data
    assert len(data["paths"]) >= 21
