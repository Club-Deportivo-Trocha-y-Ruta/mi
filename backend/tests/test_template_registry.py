import pytest
from app.schemas.notification import NotificationTemplate, DocumentTemplate
from app.services.notification.template_registry import TemplateRegistry

def test_template_registry_valid_email_context():
    registry = TemplateRegistry()
    context = {
        "athlete_first_name": "A",
        "club_name": "B",
        "season_year": "C",
        "parent_name": "D"
    }
    registry.validate_email_context(NotificationTemplate.WELCOME_ATHLETE, context)

def test_template_registry_invalid_email_context():
    registry = TemplateRegistry()
    with pytest.raises(ValueError, match="athlete_first_name"):
        registry.validate_email_context(NotificationTemplate.WELCOME_ATHLETE, {})

def test_template_registry_unknown_spec():
    registry = TemplateRegistry()
    with pytest.raises(ValueError):
        registry.get_email_spec("DOES_NOT_EXIST")

def test_template_registry_verify_templates():
    registry = TemplateRegistry()
    result = registry.verify_templates_exist()
    assert "missing" in result
