import pytest

def test_root_url(client):
    """Test that the root URL returns a 200 status code."""
    response = client.get('/')
    assert response.status_code == 200
