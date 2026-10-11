
from dataclasses import dataclass
from typing import Optional

import sqlite3


@dataclass(frozen=True)
class Farmer:
    id: int
    full_name: str
    phone: str
    county: str
    subcounty: str
    ward: str
    farm_size_acres: Optional[float]
    main_enterprise: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Farmer":
        """Convert a SQLite row into a Farmer model."""
        return cls(
            id=row["id"],
            full_name=row["full_name"],
            phone=row["phone"],
            county=row["county"],
            subcounty=row["subcounty"],
            ward=row["ward"],
            farm_size_acres=row["farm_size_acres"],
            main_enterprise=row["main_enterprise"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        """Convert the model to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "full_name": self.full_name,
            "phone": self.phone,
            "county": self.county,
            "subcounty": self.subcounty,
            "ward": self.ward,
            "farm_size_acres": self.farm_size_acres,
            "main_enterprise": self.main_enterprise,
            "created_at": self.created_at,
        }

@dataclass(frozen=True)
class Crop:
    id: int
    farmer_id: int
    name: str
    acreage: float
    planting_date: Optional[str]
    expected_harvest_date: Optional[str]
    expected_quantity: Optional[float]
    quantity_unit: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Crop":
        """Convert a SQLite row into a Crop model."""
        return cls(
            id=row["id"],
            farmer_id=row["farmer_id"],
            name=row["name"],
            acreage=row["acreage"],
            planting_date=row["planting_date"],
            expected_harvest_date=row["expected_harvest_date"],
            expected_quantity=row["expected_quantity"],
            quantity_unit=row["quantity_unit"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        """Convert the model to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "farmer_id": self.farmer_id,
            "name": self.name,
            "acreage": self.acreage,
            "planting_date": self.planting_date,
            "expected_harvest_date": self.expected_harvest_date,
            "expected_quantity": self.expected_quantity,
            "quantity_unit": self.quantity_unit,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass(frozen=True)
class ProblemReport:
    id: int
    farmer_id: int
    category: str
    crop_affected: str
    subcounty: str
    ward: str
    description: str
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ProblemReport":
        """Convert a SQLite row into a ProblemReport model."""
        return cls(
            id=row["id"],
            farmer_id=row["farmer_id"],
            category=row["category"],
            crop_affected=row["crop_affected"],
            subcounty=row["subcounty"],
            ward=row["ward"],
            description=row["description"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        """Convert the model to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "farmer_id": self.farmer_id,
            "category": self.category,
            "crop_affected": self.crop_affected,
            "subcounty": self.subcounty,
            "ward": self.ward,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
