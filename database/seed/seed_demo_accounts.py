"""
SkillMesh — Demo Accounts Seed

Creates hardcoded demo accounts for SIH judging.
Judges can log in instantly without registering.

Demo credentials (share with judges):
─────────────────────────────────────────────────────────────
Role                    Email                       Password
─────────────────────────────────────────────────────────────
Student                 student@demo.skillmesh.dev  Demo@1234
Faculty                 faculty@demo.skillmesh.dev  Demo@1234
Institution Admin       admin@demo.skillmesh.dev    Demo@1234
Industry Admin          industry@demo.skillmesh.dev Demo@1234
Recruiter               recruiter@demo.skillmesh.dev Demo@1234
Super Admin             superadmin@demo.skillmesh.dev Demo@1234
─────────────────────────────────────────────────────────────

Run AFTER:
  1. alembic upgrade head
  2. seed_master_data.py (for institutions and orgs)
  3. seed_phase2.py (for skills, roles, assessments)
  4. seed_phase4.py (for student skill scores + target role)
  5. seed_phase5.py (for learning resources)

Usage:
  DATABASE_URL=postgresql+asyncpg://... \\
  SUPABASE_URL=https://xxx.supabase.co \\
  SUPABASE_SERVICE_ROLE_KEY=... \\
  python database/seed/seed_demo_accounts.py

Safe to run multiple times — skips existing accounts.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ─── Config ───────────────────────────────────────────────────────────────────

import re

_raw_db_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://skillmesh:skillmesh_dev_password@localhost:5432/skillmesh_dev",
)

def _make_async_url(url: str) -> str:
    url = re.sub(r"^postgres://", "postgresql+asyncpg://", url)
    url = re.sub(r"^postgresql://", "postgresql+asyncpg://", url)
    url = re.sub(r"^postgresql\+psycopg2://", "postgresql+asyncpg://", url)
    return url

DATABASE_URL = _make_async_url(_raw_db_url)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

DEMO_PASSWORD = "Demo@1234"

# ─── Demo accounts ────────────────────────────────────────────────────────────

DEMO_ACCOUNTS = [
    {
        "email": "student@demo.skillmesh.dev",
        "full_name": "Arjun Sharma (Demo Student)",
        "role": "STUDENT",
        "institution": "All India Institute of Ayurveda",
        "org": None,
    },
    {
        "email": "faculty@demo.skillmesh.dev",
        "full_name": "Dr. Priya Nair (Demo Faculty)",
        "role": "FACULTY",
        "institution": "All India Institute of Ayurveda",
        "org": None,
    },
    {
        "email": "admin@demo.skillmesh.dev",
        "full_name": "Rajesh Patel (Demo Institution Admin)",
        "role": "INSTITUTION_ADMIN",
        "institution": "All India Institute of Ayurveda",
        "org": None,
    },
    {
        "email": "industry@demo.skillmesh.dev",
        "full_name": "Sneha Kulkarni (Demo Industry Admin)",
        "role": "INDUSTRY_ADMIN",
        "institution": None,
        "org": "TCS (Tata Consultancy Services)",
    },
    {
        "email": "recruiter@demo.skillmesh.dev",
        "full_name": "Vikram Mehta (Demo Recruiter)",
        "role": "RECRUITER",
        "institution": None,
        "org": "Infosys",
    },
    {
        "email": "superadmin@demo.skillmesh.dev",
        "full_name": "SkillMesh Super Admin",
        "role": "SUPER_ADMIN",
        "institution": None,
        "org": None,
    },
]


# ─── Supabase Auth helper ──────────────────────────────────────────────────────

async def create_supabase_user(email: str, full_name: str) -> str | None:
    """
    Create a user in Supabase Auth using the Admin API.
    Returns the Supabase UID, or None if Supabase is not configured.
    Auto-confirms the email so judges don't need to verify.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        import uuid
        mock_uid = str(uuid.uuid4())
        print(f"  ⚠ Supabase not configured — using mock uid for dev")
        return mock_uid

    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "password": DEMO_PASSWORD,
        "email_confirm": True,  # Skip email verification for demo
        "user_metadata": {"full_name": full_name},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code in (200, 201):
        return response.json()["id"]
    elif response.status_code == 422:
        # User already exists in Supabase — fetch their UID
        print(f"  ~ Already exists in Supabase Auth")
        return await get_supabase_uid(email)
    else:
        print(f"  ✗ Supabase error {response.status_code}: {response.text[:100]}")
        return None


async def get_supabase_uid(email: str) -> str | None:
    """Fetch UID of an existing Supabase user by email."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None

    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers, params={"per_page": 200})

    if response.status_code != 200:
        return None

    users = response.json().get("users", [])
    for user in users:
        if user.get("email") == email:
            return user["id"]
    return None


# ─── DB helpers ───────────────────────────────────────────────────────────────

async def get_institution_id(db: AsyncSession, name: str) -> str | None:
    row = await db.execute(
        text("SELECT id FROM institutions WHERE name = :name AND is_active = true"),
        {"name": name},
    )
    result = row.first()
    return str(result[0]) if result else None


async def get_org_id(db: AsyncSession, name: str) -> str | None:
    row = await db.execute(
        text("SELECT id FROM industry_organizations WHERE name = :name AND is_active = true"),
        {"name": name},
    )
    result = row.first()
    return str(result[0]) if result else None


async def user_exists(db: AsyncSession, email: str) -> bool:
    row = await db.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": email},
    )
    return row.first() is not None


async def create_local_user(
    db: AsyncSession,
    supabase_uid: str,
    email: str,
    full_name: str,
    role: str,
    institution_id: str | None,
    org_id: str | None,
) -> None:
    import uuid
    await db.execute(
        text("""
            INSERT INTO users
              (id, supabase_uid, email, full_name, role,
               institution_id, industry_org_id,
               is_active, is_verified, created_at, updated_at)
            VALUES
              (:id, :supabase_uid, :email, :full_name, :role,
               :institution_id, :org_id,
               true, true, now(), now())
            ON CONFLICT (email) DO UPDATE SET
              full_name      = EXCLUDED.full_name,
              role           = EXCLUDED.role,
              institution_id = EXCLUDED.institution_id,
              industry_org_id = EXCLUDED.industry_org_id,
              is_active      = true,
              updated_at     = now()
        """),
        {
            "id": str(uuid.uuid4()),
            "supabase_uid": supabase_uid,
            "email": email,
            "full_name": full_name,
            "role": role,
            "institution_id": institution_id,
            "org_id": org_id,
        },
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

async def seed(db: AsyncSession) -> None:
    print("SkillMesh — Demo Account Seed")
    print(f"Password for all accounts: {DEMO_PASSWORD}\n")

    for account in DEMO_ACCOUNTS:
        email = account["email"]
        print(f"Creating: {email}")

        # Resolve institution / org IDs
        institution_id = None
        org_id = None

        if account["institution"]:
            institution_id = await get_institution_id(db, account["institution"])
            if not institution_id:
                print(f"  ✗ Institution '{account['institution']}' not found")
                print(f"    → Run seed_master_data.py first")
                continue

        if account["org"]:
            org_id = await get_org_id(db, account["org"])
            if not org_id:
                print(f"  ✗ Organization '{account['org']}' not found")
                print(f"    → Run seed_master_data.py first")
                continue

        # Create Supabase Auth user
        supabase_uid = await create_supabase_user(email, account["full_name"])
        if not supabase_uid:
            print(f"  ✗ Failed to create Supabase user — skipping")
            continue

        # Create local DB record
        await create_local_user(
            db=db,
            supabase_uid=supabase_uid,
            email=email,
            full_name=account["full_name"],
            role=account["role"],
            institution_id=institution_id,
            org_id=org_id,
        )
        await db.commit()
        print(f"  ✓ {account['role']} — {account['full_name']}")

    print("\n✅ Demo accounts ready.\n")
    print("─" * 60)
    print(f"{'Role':<22} {'Email':<38} Password")
    print("─" * 60)
    for a in DEMO_ACCOUNTS:
        role_label = a["role"].replace("_", " ").title()
        print(f"{role_label:<22} {a['email']:<38} {DEMO_PASSWORD}")
    print("─" * 60)


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
