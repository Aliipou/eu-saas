"""Load test using Locust — 100 concurrent users, p95 < 200ms target.

Run with:
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 60s --headless
"""

from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class TenantPlatformUser(HttpUser):
    """Simulates a typical API consumer of the multi-tenant platform."""

    wait_time = between(0.5, 2.0)

    @task(5)
    def health_check(self) -> None:
        self.client.get("/health", name="/health")

    @task(3)
    def list_tenants(self) -> None:
        self.client.get("/api/v1/tenants?page=1&page_size=10", name="/api/v1/tenants")

    @task(2)
    def create_and_get_tenant(self) -> None:
        slug = f"load-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": f"Load Test {slug}",
            "slug": slug,
            "admin_email": f"{slug}@loadtest.example",
            "tier": "FREE",
        }
        resp = self.client.post("/api/v1/tenants", json=payload, name="/api/v1/tenants [POST]")
        if resp.status_code == 201:
            tenant_id = resp.json().get("id")
            if tenant_id:
                self.client.get(
                    f"/api/v1/tenants/{tenant_id}",
                    name="/api/v1/tenants/{id}",
                )

    @task(1)
    def get_nonexistent_tenant(self) -> None:
        fake_id = str(uuid.uuid4())
        self.client.get(
            f"/api/v1/tenants/{fake_id}",
            name="/api/v1/tenants/{id} [404]",
        )

    @task(2)
    def billing_current_costs(self) -> None:
        fake_id = str(uuid.uuid4())
        self.client.get(
            f"/api/v1/billing/tenants/{fake_id}/costs/current",
            name="/api/v1/billing/costs/current",
        )
