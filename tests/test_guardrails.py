from app.utils.logging import mask_pii


def test_mask_pii():
    masked = mask_pii("email me at demo@example.com or call +1234567890")
    assert "example" not in masked
    assert "[email-redacted]" in masked
    assert "[phone-redacted]" in masked
