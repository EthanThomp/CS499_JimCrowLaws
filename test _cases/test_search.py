"""
Simple test: search by category and verify results are returned and correct.
"""
import requests

BASE_URL = "http://localhost:5000"

def test_search_by_category():
    response = requests.get(f"{BASE_URL}/search", params={"category": "education", "limit": 50, "page": 1})

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.json()
    assert data["success"] is True, "Response success flag is not True"
    assert data["total"] > 0, "Expected at least one education law in the database"
    assert len(data["laws"]) > 0, "Expected laws in the results list"

    for law in data["laws"]:
        assert law["category"] == "education", f"Non-education law in results: {law['category']}"

    print(f"PASSED — found {data['total']} education laws, {len(data['laws'])} returned on page 1")

if __name__ == "__main__":
    test_search_by_category()
