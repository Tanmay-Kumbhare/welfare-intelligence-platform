import pytest
import uuid
from datetime import date
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.education_record import EducationRecord
from app.schemas.citizen import CitizenCreate, DemographicProfileCreate, FinancialProfileCreate, LocationProfileCreate
from app.schemas.education import EducationRecordCreate
from app.services.citizen_service import CitizenService
from app.services.profile_sync_service import ProfileSyncService
from app.models.profile_fact import ProfileFact

_TestSession = async_sessionmaker(
    create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool),
    expire_on_commit=False,
)


@pytest.mark.asyncio
async def test_education_crud_and_fact_sync():
    async with _TestSession() as session:
        # 1. Create a Citizen
        citizen_create = CitizenCreate(
            full_name="Tanmay Lakhane",
            date_of_birth=date(2002, 5, 15),
            gender="MALE",
            mobile_number="9876543210",
            citizen_type="STUDENT",
            profile_types=["STUDENT"],
            demographic=DemographicProfileCreate(
                education_level="GRADUATE",
                social_category="OBC",
                disability_status="NONE",
            ),
            financial=FinancialProfileCreate(
                annual_income=120000.0,
                employment_status="STUDENT",
                is_bpl_card_holder=False,
                is_income_tax_payer=False,
            ),
            location=LocationProfileCreate(
                address_line_1="Flat 101, Shivneri Heights",
                state="Maharashtra",
                district="Pune",
                village_city="Pune",
                pincode="411005",
                area_type="URBAN",
                same_as_permanent=True,
            ),
        )

        service = CitizenService(session)
        citizen_res = await service.register_citizen(citizen_create)
        cid = citizen_res.citizen_id

        try:
            # Verify location address persistence
            citizen_db = await service.get_citizen(cid)
            assert citizen_db.location.address_line_1 == "Flat 101, Shivneri Heights"
            assert citizen_db.location.pincode == "411005"
            assert citizen_db.location.same_as_permanent is True

            # 2. Add SSC education record
            ssc_rec = await service.add_education_record(
                cid,
                EducationRecordCreate(
                    level="10TH_SSC",
                    is_current=False,
                    passing_year=2018,
                    percentage=88.5,
                    details={"board": "MAHARASHTRA_STATE_BOARD", "institute": "City High School"},
                ),
            )
            assert ssc_rec.level == "10TH_SSC"

            # 3. Add HSC education record
            hsc_rec = await service.add_education_record(
                cid,
                EducationRecordCreate(
                    level="12TH_HSC",
                    is_current=False,
                    passing_year=2020,
                    percentage=85.0,
                    details={"stream": "SCIENCE", "board": "MAHARASHTRA_STATE_BOARD"},
                ),
            )
            assert hsc_rec.level == "12TH_HSC"

            # 4. Add UG Record (Current B.Tech)
            ug_rec = await service.add_education_record(
                cid,
                EducationRecordCreate(
                    level="UNDERGRADUATE",
                    is_current=True,
                    percentage=82.0,
                    details={
                        "degree": "B_TECH_BE",
                        "branch": "Computer Engineering",
                        "institute": "COEP Pune",
                        "university": "COEP",
                        "current_year": "THIRD_YEAR",
                        "current_semester": 6,
                        "cgpa": 8.75,
                        "cgpa_scale": 10,
                        "evaluation_type": "CGPA",
                    },
                ),
            )
            assert ug_rec.is_current is True

            # 5. Verify Facts Sync
            facts_res = await session.execute(
                select(ProfileFact).where(ProfileFact.citizen_id == cid, ProfileFact.effective_until.is_(None))
            )
            facts_map = {f.fact_code: f.fact_value for f in facts_res.scalars().all()}

            assert facts_map.get("EDUCATION_LEVEL") == "UNDERGRADUATE"
            assert facts_map.get("HIGHEST_EDUCATION_LEVEL") == "UNDERGRADUATE"
            assert facts_map.get("TENTH_PERCENTAGE") == "88.5"
            assert facts_map.get("TWELFTH_PERCENTAGE") == "85.0"
            assert facts_map.get("CURRENT_EDUCATION_LEVEL") == "UNDERGRADUATE"
            assert facts_map.get("CURRENT_DEGREE") == "B_TECH_BE"
            assert facts_map.get("CURRENT_BRANCH") == "Computer Engineering"
            assert facts_map.get("CURRENT_YEAR") == "THIRD_YEAR"
            assert facts_map.get("CURRENT_SEMESTER") == "6"
            assert facts_map.get("GRADUATION_CGPA") == "8.75"

            # 6. Delete an education record
            deleted = await service.delete_education_record(hsc_rec.record_id, cid)
            assert deleted is True

            records_remaining = await service.list_education_records(cid)
            assert len(records_remaining) == 2

        finally:
            # Clean up test citizen
            await session.execute(text("DELETE FROM tbl_citizen_master WHERE citizen_id = :cid"), {"cid": cid})
            await session.commit()
