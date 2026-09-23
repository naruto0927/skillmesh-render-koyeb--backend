"""
SkillMesh — GCAS Importer Interface

Gujarat Common Admission System (GCAS) institution data importer.
This module defines the interface and data structures for importing
institution data from GCAS into the SkillMesh institutions table.

STATUS: Interface stub only. Scraping/import not implemented yet.
        Implement as a separate task when GCAS data is available.

Usage (once implemented):
    python database/importers/gcas_importer.py --source path/to/gcas_export.json
    python database/importers/gcas_importer.py --url https://gcas.gujarat.gov.in/api/institutions

Idempotency:
    Every import uses (source='gcas', source_id=<gcas_id>) as the unique key.
    Re-running the importer updates existing records without creating duplicates.
    The partial unique index on institutions (source, source_id) enforces this.

Schema mapping (GCAS → SkillMesh institutions):
    GCAS field           → SkillMesh field
    ─────────────────────────────────────────
    gcas_id / inst_id    → source_id
    institution_name     → name
    short_name / abbr    → short_name
    inst_type            → institution_type  (mapped via TYPE_MAP below)
    city                 → city
    district             → district
    state                → state (always "Gujarat" for GCAS)
    pincode              → pincode
    address              → address
    website_url          → website
    aishe_code           → aishe_code
    (all records)        → source = "gcas"
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))


# ─── GCAS → SkillMesh institution_type mapping ────────────────────────────────

TYPE_MAP: dict[str, str] = {
    # GCAS values (lowercase, stripped) → SkillMesh InstitutionType enum
    "university": "UNIVERSITY",
    "deemed university": "DEEMED_UNIVERSITY",
    "deemed to be university": "DEEMED_UNIVERSITY",
    "autonomous college": "AUTONOMOUS_COLLEGE",
    "affiliated college": "AFFILIATED_COLLEGE",
    "college": "AFFILIATED_COLLEGE",
    "institute of technology": "INSTITUTE_OF_TECHNOLOGY",
    "nit": "INSTITUTE_OF_TECHNOLOGY",
    "iit": "INSTITUTE_OF_TECHNOLOGY",
    "polytechnic": "POLYTECHNIC",
    "other": "OTHER",
}


def map_institution_type(gcas_type: str | None) -> str:
    """Map a GCAS institution type string to a SkillMesh InstitutionType value."""
    if not gcas_type:
        return "OTHER"
    normalised = gcas_type.strip().lower()
    for key, value in TYPE_MAP.items():
        if key in normalised:
            return value
    return "OTHER"


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class GCASInstitution:
    """
    Parsed institution record from a GCAS data source.
    All fields are optional except source_id and name.
    """
    source_id: str          # Unique ID in GCAS system
    name: str               # Full institution name
    short_name: str | None = None
    institution_type: str | None = None   # Raw GCAS type string
    city: str | None = None
    district: str | None = None
    state: str = "Gujarat"
    pincode: str | None = None
    address: str | None = None
    website: str | None = None
    aishe_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)  # Original GCAS record


@dataclass
class ImportResult:
    """Result of a GCAS import run."""
    total_records: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ─── Importer interface ───────────────────────────────────────────────────────

class GCASImporter:
    """
    Base class for GCAS data importers.

    Subclass and implement `fetch_records()` for each data source:
      - GCASJsonFileImporter   — reads from a local JSON export
      - GCASApiImporter        — fetches from GCAS API endpoint
      - GCASCsvImporter        — reads from CSV export
      - GCASWebScraper         — scrapes GCAS website (last resort)

    The base `run()` method handles the upsert logic against the DB.
    """

    SOURCE = "gcas"

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://skillmesh:skillmesh_dev_password@localhost:5432/skillmesh_dev",
        )

    async def fetch_records(self) -> list[GCASInstitution]:
        """
        Fetch and parse GCAS institution records.
        IMPLEMENT THIS in subclasses.
        """
        raise NotImplementedError(
            "Subclass GCASImporter and implement fetch_records()."
        )

    async def run(self) -> ImportResult:
        """
        Run the import: fetch records, upsert into institutions table.
        Idempotent — safe to run repeatedly.
        """
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        import uuid

        result = ImportResult()
        records = await self.fetch_records()
        result.total_records = len(records)

        engine = create_async_engine(self.database_url, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as db:
            for record in records:
                try:
                    await self._upsert(db, record, result)
                except Exception as exc:
                    result.errors.append(
                        f"[{record.source_id}] {record.name}: {exc}"
                    )
                    result.skipped += 1

            await db.commit()

        await engine.dispose()
        return result

    async def _upsert(
        self,
        db: "AsyncSession",
        record: GCASInstitution,
        result: ImportResult,
    ) -> None:
        from sqlalchemy import text
        import uuid

        # Check existing by (source, source_id)
        existing = await db.execute(
            text("""
                SELECT id FROM institutions
                WHERE source = :source AND source_id = :source_id
            """),
            {"source": self.SOURCE, "source_id": record.source_id},
        )
        row = existing.first()

        inst_type = map_institution_type(record.institution_type)

        if row:
            # Update existing record
            await db.execute(
                text("""
                    UPDATE institutions SET
                        name            = :name,
                        short_name      = COALESCE(:short_name, short_name),
                        institution_type = :inst_type,
                        city            = COALESCE(:city, city),
                        district        = COALESCE(:district, district),
                        state           = :state,
                        pincode         = COALESCE(:pincode, pincode),
                        address         = COALESCE(:address, address),
                        website         = COALESCE(:website, website),
                        aishe_code      = COALESCE(:aishe_code, aishe_code),
                        updated_at      = now()
                    WHERE source = :source AND source_id = :source_id
                """),
                {
                    "name": record.name,
                    "short_name": record.short_name,
                    "inst_type": inst_type,
                    "city": record.city,
                    "district": record.district,
                    "state": record.state,
                    "pincode": record.pincode,
                    "address": record.address,
                    "website": record.website,
                    "aishe_code": record.aishe_code,
                    "source": self.SOURCE,
                    "source_id": record.source_id,
                },
            )
            result.updated += 1
        else:
            # Insert new record
            await db.execute(
                text("""
                    INSERT INTO institutions
                      (id, name, short_name, institution_type, city, district,
                       state, pincode, address, website, aishe_code,
                       source, source_id, is_active, is_verified, country,
                       created_at, updated_at)
                    VALUES
                      (:id, :name, :short_name, :inst_type, :city, :district,
                       :state, :pincode, :address, :website, :aishe_code,
                       :source, :source_id, true, false, 'India', now(), now())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "name": record.name,
                    "short_name": record.short_name,
                    "inst_type": inst_type,
                    "city": record.city,
                    "district": record.district,
                    "state": record.state,
                    "pincode": record.pincode,
                    "address": record.address,
                    "website": record.website,
                    "aishe_code": record.aishe_code,
                    "source": self.SOURCE,
                    "source_id": record.source_id,
                },
            )
            result.inserted += 1


# ─── Concrete importer stubs ──────────────────────────────────────────────────

class GCASJsonFileImporter(GCASImporter):
    """
    Import from a local JSON file exported from GCAS.

    Expected JSON format (adapt parse_record() to actual GCAS schema):
    [
      {
        "gcas_id": "GJ001",
        "institution_name": "...",
        "inst_type": "University",
        "district": "Ahmedabad",
        ...
      },
      ...
    ]

    TODO: Inspect actual GCAS JSON export and update parse_record().
    """

    def __init__(self, file_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.file_path = file_path

    async def fetch_records(self) -> list[GCASInstitution]:
        import json
        with open(self.file_path, encoding="utf-8") as f:
            raw_records = json.load(f)
        return [self.parse_record(r) for r in raw_records]

    def parse_record(self, raw: dict) -> GCASInstitution:
        """
        TODO: Update field names to match actual GCAS JSON export schema.
        This is a best-guess mapping — adjust when GCAS data is available.
        """
        return GCASInstitution(
            source_id=str(raw.get("gcas_id") or raw.get("inst_id") or raw.get("id", "")),
            name=raw.get("institution_name") or raw.get("name", ""),
            short_name=raw.get("short_name") or raw.get("abbr"),
            institution_type=raw.get("inst_type") or raw.get("type"),
            city=raw.get("city") or raw.get("town"),
            district=raw.get("district"),
            state=raw.get("state", "Gujarat"),
            pincode=str(raw.get("pincode", "")) or None,
            address=raw.get("address"),
            website=raw.get("website_url") or raw.get("website"),
            aishe_code=raw.get("aishe_code") or raw.get("aishe"),
            raw=raw,
        )


class GCASApiImporter(GCASImporter):
    """
    Import from the GCAS API endpoint (if available).
    TODO: Implement once GCAS API URL and auth are known.
    """

    def __init__(self, api_url: str, api_key: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_url = api_url
        self.api_key = api_key

    async def fetch_records(self) -> list[GCASInstitution]:
        # TODO: Implement HTTP fetch from GCAS API
        # import httpx
        # headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(self.api_url, headers=headers)
        #     raw_records = response.json()
        # return [self.parse_record(r) for r in raw_records]
        raise NotImplementedError("GCASApiImporter.fetch_records() not yet implemented.")

    def parse_record(self, raw: dict) -> GCASInstitution:
        # TODO: Adapt to actual GCAS API response schema
        raise NotImplementedError("GCASApiImporter.parse_record() not yet implemented.")


# ─── CLI entry point ──────────────────────────────────────────────────────────

async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import GCAS institution data")
    parser.add_argument("--file", help="Path to GCAS JSON export file")
    parser.add_argument("--url", help="GCAS API URL")
    parser.add_argument("--api-key", help="GCAS API key (if required)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse records but don't write to DB")
    args = parser.parse_args()

    if args.file:
        importer = GCASJsonFileImporter(file_path=args.file)
        print(f"Importing from file: {args.file}")
    elif args.url:
        importer = GCASApiImporter(api_url=args.url, api_key=args.api_key)
        print(f"Importing from API: {args.url}")
    else:
        print("Error: Provide --file or --url")
        print("\nInterface is ready. To use:")
        print("  python gcas_importer.py --file /path/to/gcas_export.json")
        print("  python gcas_importer.py --url https://gcas.gujarat.gov.in/api/institutions")
        return

    if args.dry_run:
        records = await importer.fetch_records()
        print(f"Dry run — parsed {len(records)} records:")
        for r in records[:5]:
            print(f"  [{r.source_id}] {r.name} ({r.district}, {r.state})")
        if len(records) > 5:
            print(f"  … and {len(records) - 5} more")
        return

    result = await importer.run()
    print(f"\n✅ Import complete:")
    print(f"   Total:    {result.total_records}")
    print(f"   Inserted: {result.inserted}")
    print(f"   Updated:  {result.updated}")
    print(f"   Skipped:  {result.skipped}")
    if result.errors:
        print(f"\n⚠ Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            print(f"  {err}")


if __name__ == "__main__":
    asyncio.run(main())
