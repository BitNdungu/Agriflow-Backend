
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
