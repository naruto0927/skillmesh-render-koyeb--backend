"""
SkillMesh — Master Data Seed (Phase 6 prerequisite)

Seeds realistic institution and industry organization data:
- Gujarat institutions prepared for GCAS import
  (aishe_code, district, source fields populated where known)
- Industry organizations covering major sectors

This seed is idempotent — safe to run multiple times.
Uses (source, source_id) for institutions so GCAS import can later
upsert without creating duplicates.

Run with:
  DATABASE_URL=postgresql+asyncpg://... python database/seed/seed_master_data.py
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://skillmesh:skillmesh_dev_password@localhost:5432/skillmesh_dev",
)

# ─── Institutions ─────────────────────────────────────────────────────────────
# source="manual" for now; source="gcas" + source_id will be added by GCAS importer
# aishe_code is the All India Survey on Higher Education unique code

INSTITUTIONS = [
    # ── Central / National institutions ──
    {
        "name": "All India Institute of Ayurveda",
        "short_name": "AIIA",
        "type": "UNIVERSITY",
        "city": "New Delhi",
        "district": "South Delhi",
        "state": "Delhi",
        "website": "https://aiia.gov.in",
        "aishe_code": "U-0670",
        "desc": "Premier institute under Ministry of Ayush for Ayurveda research and education.",
    },
    {
        "name": "Indian Institute of Technology Delhi",
        "short_name": "IIT Delhi",
        "type": "INSTITUTE_OF_TECHNOLOGY",
        "city": "New Delhi",
        "district": "South West Delhi",
        "state": "Delhi",
        "website": "https://iitd.ac.in",
        "aishe_code": "U-0571",
        "desc": "Premier technical institute offering undergraduate and postgraduate programs.",
    },
    # ── Gujarat institutions ──
    {
        "name": "Gujarat Technological University",
        "short_name": "GTU",
        "type": "UNIVERSITY",
        "city": "Ahmedabad",
        "district": "Ahmedabad",
        "state": "Gujarat",
        "website": "https://gtu.ac.in",
        "aishe_code": "U-0392",
        "desc": "State technical university affiliating over 400 engineering and management colleges.",
    },
    {
        "name": "Sardar Vallabhbhai National Institute of Technology",
        "short_name": "SVNIT Surat",
        "type": "INSTITUTE_OF_TECHNOLOGY",
        "city": "Surat",
        "district": "Surat",
        "state": "Gujarat",
        "website": "https://svnit.ac.in",
        "aishe_code": "U-0393",
        "desc": "NIT offering B.Tech, M.Tech, and PhD programs in engineering disciplines.",
    },
    {
        "name": "Nirma University",
        "short_name": "Nirma",
        "type": "DEEMED_UNIVERSITY",
        "city": "Ahmedabad",
        "district": "Ahmedabad",
        "state": "Gujarat",
        "website": "https://nirmauni.ac.in",
        "aishe_code": "U-0394",
        "desc": "Deemed university with strong industry linkages in engineering and management.",
    },
    {
        "name": "Dhirubhai Ambani Institute of Information and Communication Technology",
        "short_name": "DA-IICT",
        "type": "DEEMED_UNIVERSITY",
        "city": "Gandhinagar",
        "district": "Gandhinagar",
        "state": "Gujarat",
        "website": "https://daiict.ac.in",
        "aishe_code": "U-0395",
        "desc": "Specialised institute focused on ICT, data science, and communication technology.",
    },
    {
        "name": "L.D. College of Engineering",
        "short_name": "LDCE",
        "type": "AUTONOMOUS_COLLEGE",
        "city": "Ahmedabad",
        "district": "Ahmedabad",
        "state": "Gujarat",
        "website": "https://ldce.ac.in",
        "aishe_code": "C-41234",
        "desc": "One of the oldest and largest government engineering colleges in Gujarat.",
    },
    {
        "name": "Charotar University of Science and Technology",
        "short_name": "CHARUSAT",
        "type": "DEEMED_UNIVERSITY",
        "city": "Anand",
        "district": "Anand",
        "state": "Gujarat",
        "website": "https://charusat.ac.in",
        "desc": "Multi-disciplinary deemed university in Charotar region.",
    },
    {
        "name": "Silver Oak University",
        "short_name": "SOU",
        "type": "UNIVERSITY",
        "city": "Ahmedabad",
        "district": "Ahmedabad",
        "state": "Gujarat",
        "website": "https://silveroakuni.ac.in",
        "desc": "Private university offering engineering, pharmacy, and management programs.",
    },
    {
        "name": "Marwadi University",
        "short_name": "MU Rajkot",
        "type": "UNIVERSITY",
        "city": "Rajkot",
        "district": "Rajkot",
        "state": "Gujarat",
        "website": "https://marwadiuniversity.ac.in",
        "desc": "Private university with strong focus on industry-ready engineering education.",
    },
    {
        "name": "Government Engineering College Rajkot",
        "short_name": "GEC Rajkot",
        "type": "AUTONOMOUS_COLLEGE",
        "city": "Rajkot",
        "district": "Rajkot",
        "state": "Gujarat",
        "website": "https://gecrajkot.ac.in",
        "desc": "Government engineering college affiliated to GTU.",
    },
    {
        "name": "Sardar Patel University",
        "short_name": "SPU",
        "type": "UNIVERSITY",
        "city": "Vallabh Vidyanagar",
        "district": "Anand",
        "state": "Gujarat",
        "website": "https://spu.ac.in",
        "aishe_code": "U-0396",
        "desc": "One of Gujarat's oldest universities with comprehensive faculties.",
    },
    {
        "name": "Veer Narmad South Gujarat University",
        "short_name": "VNSGU",
        "type": "UNIVERSITY",
        "city": "Surat",
        "district": "Surat",
        "state": "Gujarat",
        "website": "https://vnsgu.ac.in",
        "desc": "State university affiliating colleges across south Gujarat.",
    },
    # ── Delhi / NCR ──
    {
        "name": "Delhi Technological University",
        "short_name": "DTU",
        "type": "AUTONOMOUS_COLLEGE",
        "city": "New Delhi",
        "district": "North West Delhi",
        "state": "Delhi",
        "website": "https://dtu.ac.in",
        "aishe_code": "U-0574",
        "desc": "State technical university with strong placement record.",
    },
    {
        "name": "Jamia Millia Islamia",
        "short_name": "JMI",
        "type": "UNIVERSITY",
        "city": "New Delhi",
        "district": "South East Delhi",
        "state": "Delhi",
        "website": "https://jmi.ac.in",
        "aishe_code": "U-0576",
        "desc": "Central university offering diverse programs across science and arts.",
    },
]

# ─── Industry Organizations ───────────────────────────────────────────────────

ORGANIZATIONS = [
    # Software & IT
    {"name": "TCS (Tata Consultancy Services)", "sector": "Software & IT Services", "city": "Mumbai"},
    {"name": "Infosys", "sector": "Software & IT Services", "city": "Bengaluru"},
    {"name": "Wipro", "sector": "Software & IT Services", "city": "Bengaluru"},
    {"name": "HCL Technologies", "sector": "Software & IT Services", "city": "Noida"},
    {"name": "Tech Mahindra", "sector": "Software & IT Services", "city": "Pune"},
    # Gujarat-based companies
    {"name": "Infibeam Avenues", "sector": "FinTech", "city": "Ahmedabad"},
    {"name": "Adani Digital Labs", "sector": "Software & IT Services", "city": "Ahmedabad"},
    {"name": "Torrent Group IT", "sector": "Software & IT Services", "city": "Ahmedabad"},
    {"name": "CEPT Research and Development Foundation", "sector": "Research & Consulting", "city": "Ahmedabad"},
    {"name": "IDeaS Revenue Solutions", "sector": "Data Analytics & AI", "city": "Ahmedabad"},
    # Data & AI
    {"name": "DataCore Analytics", "sector": "Data Analytics & AI", "city": "Hyderabad"},
    {"name": "Mu Sigma", "sector": "Data Analytics & AI", "city": "Bengaluru"},
    # Cloud & DevOps
    {"name": "CloudNine Infrastructure", "sector": "Cloud & DevOps", "city": "Pune"},
    {"name": "Rackspace Technology India", "sector": "Cloud & DevOps", "city": "Hyderabad"},
    # Healthcare
    {"name": "Ayush Digital Health", "sector": "Healthcare Technology", "city": "New Delhi"},
    {"name": "Practo Technologies", "sector": "Healthcare Technology", "city": "Bengaluru"},
    # Cybersecurity
    {"name": "SecureNet Cyber", "sector": "Cybersecurity", "city": "Mumbai"},
    {"name": "Quick Heal Technologies", "sector": "Cybersecurity", "city": "Pune"},
    # Others
    {"name": "Zydus Lifesciences", "sector": "Pharmaceuticals", "city": "Ahmedabad"},
    {"name": "ISRO Space Applications Centre", "sector": "Space Technology & Research", "city": "Ahmedabad"},
]


async def seed(db: AsyncSession) -> None:
    print("Master data seed — institutions and organizations\n")

    # ── Institutions ──────────────────────────────────────────────────────────
    print("Seeding institutions…")
    inst_count = 0
    for inst in INSTITUTIONS:
        result = await db.execute(
            text("SELECT id FROM institutions WHERE name = :name"),
            {"name": inst["name"]},
        )
        existing = result.first()

        if existing:
            # Update with new fields if they exist
            await db.execute(
                text("""
                    UPDATE institutions SET
                        short_name = COALESCE(:short_name, short_name),
                        district = COALESCE(:district, district),
                        aishe_code = COALESCE(:aishe_code, aishe_code),
                        website = COALESCE(:website, website),
                        description = COALESCE(:desc, description),
                        source = 'manual',
                        updated_at = now()
                    WHERE name = :name
                """),
                {
                    "name": inst["name"],
                    "short_name": inst.get("short_name"),
                    "district": inst.get("district"),
                    "aishe_code": inst.get("aishe_code"),
                    "website": inst.get("website"),
                    "desc": inst.get("desc"),
                },
            )
            print(f"  ~ Updated: {inst['name']}")
        else:
            await db.execute(
                text("""
                    INSERT INTO institutions
                      (id, name, short_name, institution_type, city, district, state,
                       website, description, aishe_code, source, is_active, is_verified,
                       country, created_at, updated_at)
                    VALUES
                      (:id, :name, :short_name, :itype, :city, :district, :state,
                       :website, :desc, :aishe_code, 'manual', true, true,
                       'India', now(), now())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "name": inst["name"],
                    "short_name": inst.get("short_name"),
                    "itype": inst.get("type", "OTHER"),
                    "city": inst.get("city"),
                    "district": inst.get("district"),
                    "state": inst.get("state"),
                    "website": inst.get("website"),
                    "desc": inst.get("desc"),
                    "aishe_code": inst.get("aishe_code"),
                },
            )
            print(f"  + Added: {inst['name']}")
            inst_count += 1

    # ── Organizations ─────────────────────────────────────────────────────────
    print("\nSeeding industry organizations…")
    org_count = 0
    for org in ORGANIZATIONS:
        result = await db.execute(
            text("SELECT id FROM industry_organizations WHERE name = :name"),
            {"name": org["name"]},
        )
        if result.first():
            print(f"  ~ Exists: {org['name']}")
            continue

        await db.execute(
            text("""
                INSERT INTO industry_organizations
                  (id, name, industry_sector, headquarters_city,
                   is_active, is_verified, headquarters_country,
                   created_at, updated_at)
                VALUES
                  (:id, :name, :sector, :city,
                   true, true, 'India', now(), now())
            """),
            {
                "id": str(uuid.uuid4()),
                "name": org["name"],
                "sector": org.get("sector"),
                "city": org.get("city"),
            },
        )
        print(f"  + Added: {org['name']}")
        org_count += 1

    await db.commit()

    print(f"\n✅ Master data seed complete.")
    print(f"   Institutions: {inst_count} added")
    print(f"   Organizations: {org_count} added")
    print("\nGCAS import note:")
    print("  All institutions seeded with source='manual'.")
    print("  GCAS importer should upsert on (source='gcas', source_id=<gcas_id>)")
    print("  to avoid duplicates with manually-seeded records.")


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
