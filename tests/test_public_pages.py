from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_public_sms_policy_pages_are_accessible_and_linked(
    tmp_path: Path,
) -> None:
    application = create_app(tmp_path / "coachline.sqlite3")

    with TestClient(application) as client:
        privacy = client.get("/privacy")
        terms = client.get("/terms")
        consent = client.get("/sms-consent")

    for response in (privacy, terms, consent):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert 'href="/privacy"' in response.text
        assert 'href="/terms"' in response.text
        assert 'href="/sms-consent"' in response.text
        assert "+1626" not in response.text


def test_privacy_policy_contains_required_mobile_disclosures(
    tmp_path: Path,
) -> None:
    application = create_app(tmp_path / "coachline.sqlite3")

    with TestClient(application) as client:
        response = client.get("/privacy")

    assert "Mobile numbers, SMS opt-in data" in response.text
    assert "not shared with third parties or affiliates" in response.text
    assert "marketing or promotional purposes" in response.text
    assert "Message frequency varies" in response.text
    assert "Message and data rates may apply" in response.text
    assert "specialflavorz@gmail.com" in response.text


def test_terms_contain_required_sms_program_disclosures(tmp_path: Path) -> None:
    application = create_app(tmp_path / "coachline.sqlite3")

    with TestClient(application) as client:
        response = client.get("/terms")

    assert "Coachline owner-only development pilot" in response.text
    assert "Message frequency varies" in response.text
    assert "Message and data rates may apply" in response.text
    assert "Reply STOP to unsubscribe" in response.text
    assert "Reply HELP for help" in response.text
    assert "Carriers are not liable for delayed or undelivered messages" in response.text


def test_consent_page_documents_owner_only_voluntary_enrollment(
    tmp_path: Path,
) -> None:
    application = create_app(tmp_path / "coachline.sqlite3")

    with TestClient(application) as client:
        response = client.get("/sms-consent")

    assert "account owner is the only SMS recipient" in response.text
    assert "No public enrollment is offered" in response.text
    assert "SMS consent is optional" in response.text
    assert "purchased, rented, shared, or scraped contact lists" in response.text
