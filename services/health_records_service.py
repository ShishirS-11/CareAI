from __future__ import annotations

from typing import Any


class HealthRecordsService:
    """Patient-scoped CRUD operations. Supabase RLS remains the security boundary."""

    TABLES = {"health_conditions", "patient_allergies", "current_medications", "previous_prescriptions"}

    def __init__(self, client: Any, user_id: str):
        self.client = client
        self.user_id = user_id

    def list_records(self, table: str, order_column: str = "created_at") -> list[dict]:
        if table not in self.TABLES:
            raise ValueError("Unsupported health record type")
        response = self.client.table(table).select("*").eq("user_id", self.user_id).order(order_column, desc=True).execute()
        return response.data or []

    def add_record(self, table: str, values: dict) -> dict:
        if table not in self.TABLES:
            raise ValueError("Unsupported health record type")
        response = self.client.table(table).insert({**values, "user_id": self.user_id}).execute()
        if not response.data:
            raise RuntimeError("The record was not saved. Please try again.")
        return response.data[0]

    def delete_record(self, table: str, record_id: str) -> None:
        if table not in self.TABLES:
            raise ValueError("Unsupported health record type")
        self.client.table(table).delete().eq("id", record_id).eq("user_id", self.user_id).execute()
