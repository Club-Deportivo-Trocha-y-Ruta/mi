import pytest
from app.schemas.notification import DocumentRequest, DocumentTemplate, DocumentFormat
from app.services.notification.template_registry import TemplateRegistry
from app.services.notification.document_generator import DocumentGenerator

@pytest.mark.asyncio
async def test_generate_pdf(mocker):
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    
    # Evitar problemas nativos de WeasyPrint en macOS
    mocker.patch.object(
        generator, 
        "_generate_pdf", 
        return_value=__import__("app.schemas.notification", fromlist=["GeneratedDocument", "DocumentFormat"]).GeneratedDocument(
            filename="fake.pdf", format=DocumentFormat.PDF, data=b"%PDF_FAKE", content_type="application/pdf"
        )
    )
    
    req = DocumentRequest(
        template=DocumentTemplate.ANTHROPOMETRY_REPORT,
        format=DocumentFormat.PDF,
        context={
            "athlete_first_name": "F", "athlete_last_name": "L",
            "birth_date": "2010-01-01", "sex": "M", "club_name": "C",
            "evaluation_date": "2024-01-01", "weight_kg": 50,
            "standing_height_cm": 150, "sitting_height_cm": 75,
            "maturation_status": "Pre-PHV", "maturity_offset": -2.0,
            "age_at_phv": 14.0
        }
    )
    doc = await generator.generate(req)
    assert doc.data.startswith(b'%PDF')

@pytest.mark.asyncio
async def test_generate_docx():
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)
    req = DocumentRequest(
        template=DocumentTemplate.MEDICAL_CLEARANCE,
        format=DocumentFormat.DOCX,
        context={
            "athlete_first_name": "F", "athlete_last_name": "L",
            "birth_date": "2010-01-01", "club_name": "C",
            "season_year": 2024, "medical_conditions": ["A"]
        }
    )
    doc = await generator.generate(req)
    assert doc.data.startswith(b'PK')
