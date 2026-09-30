"""Comprehensive Locust load testing scenario covering full work management lifecycle."""

import random
import uuid

from locust import HttpUser, between, task


class WorkManagementUser(HttpUser):
    """Simulates realistic user lifecycle across all major work management domains."""

    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        """Register, authenticate, create organization, and initialize resource state."""
        self.org_id: str = ""
        self.project_ids: list[str] = []
        self.task_ids: list[tuple[str, str]] = []

        unique_id = uuid.uuid4().hex[:10]
        self.email = f"loadtest_{unique_id}@example.com"
        self.password = "Password123!"

        # 1. Register user
        register_payload = {
            "email": self.email,
            "password": self.password,
            "full_name": f"Load User {unique_id}",
        }
        with self.client.post(
            "/api/v1/auth/register",
            json=register_payload,
            name="/api/v1/auth/register",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"Registration failed: {response.status_code} - {response.text}")
                return

        # 2. Authenticate user
        login_payload = {
            "email": self.email,
            "password": self.password,
        }
        with self.client.post(
            "/api/v1/auth/login",
            json=login_payload,
            name="/api/v1/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                access_token = data.get("access_token")
                self.client.headers.update({"Authorization": f"Bearer {access_token}"})
            else:
                response.failure(f"Login failed: {response.status_code} - {response.text}")
                return

        # 3. Create initial organization
        org_slug = f"org-{uuid.uuid4().hex[:8]}"
        org_payload = {
            "name": f"Org {org_slug}",
            "slug": org_slug,
        }
        with self.client.post(
            "/api/v1/orgs",
            json=org_payload,
            name="/api/v1/orgs [create]",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.org_id = response.json().get("id", "")
            else:
                response.failure(f"Org creation failed: {response.status_code} - {response.text}")

    @task(4)
    def health_and_ready(self) -> None:
        """Check operational liveness and readiness probes."""
        self.client.get("/health", name="/health")
        self.client.get("/ready", name="/ready")

    @task(3)
    def user_profile_and_org(self) -> None:
        """Fetch authenticated user profile and active organization details."""
        if not self.org_id:
            return
        self.client.get("/api/v1/auth/me", name="/api/v1/auth/me")
        self.client.get(f"/api/v1/orgs/{self.org_id}", name="/api/v1/orgs/[org_id]")

    @task(2)
    def create_project(self) -> None:
        """Create a new project under the organization."""
        if not self.org_id:
            return
        project_name = f"Project {uuid.uuid4().hex[:6]}"
        payload = {
            "name": project_name,
            "description": "Load test generated project",
        }
        with self.client.post(
            f"/api/v1/orgs/{self.org_id}/projects",
            json=payload,
            name="/api/v1/orgs/[org_id]/projects [create]",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                project_id = response.json().get("id")
                if project_id:
                    self.project_ids.append(project_id)

    @task(3)
    def query_projects(self) -> None:
        """List projects or fetch details for an existing project."""
        if not self.org_id or not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        self.client.get(
            f"/api/v1/orgs/{self.org_id}/projects",
            name="/api/v1/orgs/[org_id]/projects [list]",
        )
        self.client.get(
            f"/api/v1/orgs/{self.org_id}/projects/{project_id}",
            name="/api/v1/orgs/[org_id]/projects/[project_id] [get]",
        )

    @task(2)
    def create_task(self) -> None:
        """Create a new task inside a randomly selected project."""
        if not self.org_id or not self.project_ids:
            return
        project_id = random.choice(self.project_ids)
        task_title = f"Task {uuid.uuid4().hex[:6]}"
        payload = {
            "title": task_title,
            "description": "Load test generated task description",
            "priority": "MEDIUM",
        }
        with self.client.post(
            f"/api/v1/orgs/{self.org_id}/projects/{project_id}/tasks",
            json=payload,
            name="/api/v1/orgs/[org_id]/projects/[project_id]/tasks [create]",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                task_id = response.json().get("id")
                if task_id:
                    self.task_ids.append((project_id, task_id))

    @task(3)
    def inspect_or_update_task(self) -> None:
        """Get task details or transition its status."""
        if not self.org_id or not self.task_ids:
            return
        project_id, task_id = random.choice(self.task_ids)
        self.client.get(
            f"/api/v1/orgs/{self.org_id}/projects/{project_id}/tasks/{task_id}",
            name="/api/v1/orgs/[org_id]/projects/[project_id]/tasks/[task_id] [get]",
        )
        new_status = random.choice(["IN_PROGRESS", "IN_REVIEW", "DONE", "TODO"])
        self.client.patch(
            f"/api/v1/orgs/{self.org_id}/projects/{project_id}/tasks/{task_id}",
            json={"status": new_status},
            name="/api/v1/orgs/[org_id]/projects/[project_id]/tasks/[task_id] [patch]",
        )

    @task(2)
    def comment_on_task(self) -> None:
        """Add a comment to an existing task."""
        if not self.org_id or not self.task_ids:
            return
        project_id, task_id = random.choice(self.task_ids)
        payload = {
            "content": f"Automated performance test comment {uuid.uuid4().hex[:6]}",
        }
        self.client.post(
            f"/api/v1/orgs/{self.org_id}/projects/{project_id}/tasks/{task_id}/comments",
            json=payload,
            name="/api/v1/orgs/[org_id]/projects/[project_id]/tasks/[task_id]/comments [create]",
        )

    @task(1)
    def list_notifications(self) -> None:
        """List notifications for the current user."""
        self.client.get(
            "/api/v1/notifications",
            name="/api/v1/notifications [list]",
        )

    @task(1)
    def list_audit_logs(self) -> None:
        """List audit logs for the organization."""
        if not self.org_id:
            return
        self.client.get(
            f"/api/v1/orgs/{self.org_id}/audit-logs",
            name="/api/v1/orgs/[org_id]/audit-logs [list]",
        )
