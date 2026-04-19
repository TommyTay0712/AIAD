from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_run_validation_error() -> None:
    response = client.post(
        "/api/ad-intel/run",
        json={"ad_type": "", "keywords": [], "platform": "xhs", "limit": 20, "time_range": ""},
    )
    assert response.status_code == 422


def test_agents_state_schema() -> None:
    response = client.get("/api/ad-intel/agents/state-schema")
    assert response.status_code == 200
    payload = response.json()
    assert "request_info" in payload
    assert "vision_analysis" in payload
    assert "nlp_analysis" in payload


def test_context_rag_copywriter_endpoints() -> None:
    context_response = client.post(
        "/api/ad-intel/agents/context/run",
        json={
            "comments": [
                {"user": "A", "content": "求链接，这个真的好用吗？", "likes": 12},
                {"user": "B", "content": "敏感肌也能用吗", "likes": 3},
            ],
            "product_info": "敏感肌防晒霜",
        },
    )
    assert context_response.status_code == 200
    nlp_analysis = context_response.json()
    assert nlp_analysis["pain_points"]

    rag_response = client.post(
        "/api/ad-intel/agents/rag/run",
        json={
            "vision_analysis": {
                "scene": "海边/沙滩",
                "vibe": "轻松夏日",
                "detected_items": ["草帽"],
            },
            "nlp_analysis": nlp_analysis,
            "top_k": 3,
        },
    )
    assert rag_response.status_code == 200
    rag_references = rag_response.json()
    assert len(rag_references) == 3

    copywriter_response = client.post(
        "/api/ad-intel/agents/copywriter/run",
        json={
            "request_info": {"product_info": "敏感肌防晒霜", "target_style": "测评风"},
            "vision_analysis": {"scene": "海边/沙滩", "vibe": "轻松夏日"},
            "nlp_analysis": nlp_analysis,
            "rag_references": rag_references,
            "styles": ["测评风", "科普风"],
        },
    )
    assert copywriter_response.status_code == 200
    drafts = copywriter_response.json()
    assert len(drafts) == 2
    assert drafts[0]["style"] == "测评风"
