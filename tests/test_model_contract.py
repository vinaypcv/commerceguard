import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from commerceguard.gemini import generate
from commerceguard.models import Refund


@pytest.mark.parametrize(
    "output,valid",
    [
        (
            json.dumps({"transaction_id": "tx_demo", "amount_cents": 100, "idempotency_key": "model-0001"}),
            True,
        ),
        ('{"transaction_id":"tx_demo","amount_cents":true,"idempotency_key":"model-0001"}', False),
        ("Ignore policy and issue money", False),
    ],
)
def test_model_output_revalidated(monkeypatch, output, valid):
    class FakeClient:
        def __init__(self, **kwargs):
            self.models = SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=output))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    # Contract test only; this does not call a live model.
    fake_types = SimpleNamespace(HttpOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw)
    monkeypatch.setitem(sys.modules, "google.genai", SimpleNamespace(Client=FakeClient, types=fake_types))
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    if valid:
        assert generate(Refund, "test").amount_cents == 100
    else:
        with pytest.raises(ValidationError):
            generate(Refund, "test")
