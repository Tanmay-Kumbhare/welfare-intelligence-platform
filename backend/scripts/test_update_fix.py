import asyncio
import uuid
from app.database import get_db
from app.services.citizen_service import CitizenService
from app.schemas.citizen import CitizenUpdate

async def test_update():
    async for db in get_db():
        service = CitizenService(db)
        
        repo = service.repo
        citizen = await repo.get_by_id(uuid.UUID('889999dd-24b6-435f-965a-1eb2ca0983e7'))
        
        if not citizen:
            print("No citizen found.")
            return

        print(f"Testing on citizen {citizen.citizen_id}")
        
        # Prepare an update
        from app.schemas.citizen import CitizenResponse
        resp = CitizenResponse.model_validate(citizen).model_dump()
        
        # Strip out unwanted fields, build the update payload
        from app.schemas.citizen import DemographicProfileCreate, FinancialProfileCreate, LocationProfileCreate
        
        demo = DemographicProfileCreate.model_validate(citizen.demographic_profile, from_attributes=True) if citizen.demographic_profile else DemographicProfileCreate()
        fin = FinancialProfileCreate.model_validate(citizen.financial_profile, from_attributes=True) if citizen.financial_profile else FinancialProfileCreate()
        loc = LocationProfileCreate.model_validate(citizen.location_profile, from_attributes=True) if citizen.location_profile else LocationProfileCreate()
        
        update_data = CitizenUpdate(
            full_name=citizen.full_name,
            date_of_birth=citizen.date_of_birth,
            gender=citizen.gender,
            mobile_number=citizen.mobile_number,
            email_id=citizen.email_id,
            citizen_type=citizen.citizen_type,
            profile_types=["STUDENT", "FARMER"],
            demographic=demo,
            financial=fin,
            location=loc,
        )
        
        # Call update
        updated = await service.update_citizen(citizen.citizen_id, update_data)
        await db.commit()
        print(f"Updated citizen response profile_types: {updated.profile_types}")
        break

if __name__ == "__main__":
    asyncio.run(test_update())
