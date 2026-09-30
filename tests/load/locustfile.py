"""Locust load testing scenarios for Project & Work Management API."""

import uuid

from locust import HttpUser, between, task


class WorkManagementUser(HttpUser):
    """Simulates realistic user lifecycle: register, authenticate, query, and mutate."""

    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        """Register and authenticate user, setting session Authorization header."""
        unique_id = uuid.uuid4().hex[:10]
        self.email = f"loadtest_{unique_id}@example.com"
        self.password = "Password123!"

        # Register user
        register_payload = {
            "email": self.email,
            "password": self.password,
            "full_name": f"Load User {unique_id}",
        }
        with self.client.post(
            "/api/v1/auth/register",
            json=register_payload,
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"Registration failed: {response.status_code} - {response.text}")
                return

        # Authenticate user
        login_payload = {
            "email": self.email,
            "password": self.password,
        }
        with self.client.post(
            "/api/v1/auth/login",
            json=login_payload,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                access_token = data.get("access_token")
                self.client.headers.update({"Authorization": f"Bearer {access_token}"})
            else:
                response.failure(f"Login failed: {response.status_code} - {response.text}")

    @task(3)
    def health_and_ready(self) -> None:
        """Check operational liveness and readiness probes."""
        self.client.get("/health")
        self.client.get("/ready")

    @task(2)
    def current_user(self) -> None:
        """Fetch profile for currently authenticated user."""
        self.client.get("/api/v1/auth/me")

    @task(1)
    def organization_operations(self) -> None:
        """Create an organization and list memberships."""
        org_slug = f"org-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": f"Org {org_slug}",
            "slug": org_slug,
        }
        self.client.post("/api/v1/orgs", json=payload)
        self.client.get("/api/v1/orgs")
