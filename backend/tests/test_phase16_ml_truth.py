import pytest


@pytest.mark.asyncio
async def test_sentiment_requires_actual_text_and_never_falls_back(monkeypatch):
    from ai.inference_manager import inference_manager
    from app.services.ai.sentiment import sentiment_service

    async def unavailable(_texts):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(inference_manager, "analyze_sentiment", unavailable)
    with pytest.raises(ValueError, match="ACTUAL"):
        await sentiment_service.analyze(["comment"], source_type="SIMULATED")
    with pytest.raises(RuntimeError, match="UNAVAILABLE"):
        await sentiment_service.analyze(["comment"], source_type="ACTUAL")


@pytest.mark.asyncio
async def test_lead_prediction_is_unavailable_without_model(monkeypatch):
    from ai.inference_manager import inference_manager
    from app.services.ai.lead_prediction import lead_prediction_service

    async def unavailable(*_args):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(inference_manager, "predict_lead", unavailable)
    with pytest.raises(RuntimeError, match="UNAVAILABLE"):
        await lead_prediction_service.predict(
            clicks=1, views=10, time_spent_seconds=0, prior_purchases=0,
            source_platform="telegram", device="unknown", age_group="unknown",
            location_tier=0,
        )


def test_xgboost_training_requires_boolean_actual_conversion_labels():
    from ai.lead.xgboost_service import eligible_training_records

    records = [
        {"source_type": "ACTUAL", "converted": True},
        {"source_type": "ACTUAL", "converted": False},
        {"source_type": "ACTUAL", "converted": 1},
        {"source_type": "ACTUAL", "converted": 0},
        {"source_type": "SIMULATED", "converted": True},
        {"source_type": "ACTUAL", "likes": 4},
    ]
    assert eligible_training_records(records) == records[:2]


@pytest.mark.asyncio
async def test_lstm_rejects_short_or_incomplete_actual_history():
    from app.services.ai.lstm_forecast import lstm_forecast_service

    rows = [
        {
            "likes": 1, "shares": 1, "comments": 1, "ctr": 0.1,
            "reach": 10, "source_type": "ACTUAL", "event_date": index,
        }
        for index in range(13)
    ]
    with pytest.raises(ValueError, match="Insufficient ACTUAL history"):
        await lstm_forecast_service.forecast("campaign", rows)

    rows.append({"source_type": "ACTUAL", "event_date": 13})
    with pytest.raises(ValueError, match="INVALID_HISTORY"):
        await lstm_forecast_service.forecast("campaign", rows)


@pytest.mark.asyncio
async def test_keyword_fallback_is_reported_as_fallback(monkeypatch):
    """
    DistilBERT's keyword fallback is a guess, not a model output. It must come
    back as FALLBACK with no model name or version — reported as PREDICTED it
    was attributed a DistilBERT model and a model_version_id downstream.
    """
    from ai.inference_manager import inference_manager
    from ai.sentiment.distilbert_service import _keyword_fallback
    from app.services.ai.sentiment import sentiment_service

    async def keyword_results(_texts):
        return [_keyword_fallback("great product")]

    monkeypatch.setattr(inference_manager, "analyze_sentiment", keyword_results)
    result = (await sentiment_service.analyze(
        ["great product"], source_type="ACTUAL", source_system="telegram",
    ))["results"][0]

    assert result["model_used"] == "keyword-fallback"
    assert result["source_type"] == "FALLBACK"
    assert result["is_fallback"] is True
    assert result["model_name"] is None
    assert result["model_version"] is None
    assert result["source_system"] == "keyword_fallback"
    # The input really is ACTUAL text — only the output is a fallback.
    assert result["input_source_type"] == "ACTUAL"


@pytest.mark.asyncio
async def test_model_sentiment_result_still_reports_predicted(monkeypatch):
    """
    Counterpart of the test above: a real model result must stay PREDICTED, so
    the fallback provenance cannot be "fixed" by labelling everything FALLBACK.
    """
    from ai.inference_manager import inference_manager
    from ai.sentiment.distilbert_service import _normalize
    from app.services.ai.sentiment import sentiment_service

    async def model_results(_texts):
        return [_normalize("great product", [
            {"label": "POSITIVE", "score": 0.98},
            {"label": "NEGATIVE", "score": 0.01},
        ])]

    monkeypatch.setattr(inference_manager, "analyze_sentiment", model_results)
    result = (await sentiment_service.analyze(
        ["great product"], source_type="ACTUAL", source_system="telegram",
    ))["results"][0]

    assert result["source_type"] == "PREDICTED"
    assert result["is_fallback"] is False
    assert result["model_name"] == "DistilBERT SST-2"
    assert result["model_version"] == "distilbert"
    assert result["source_system"] == "telegram"


def test_qwen_vl_without_utils_returns_fallback_without_running_the_model(monkeypatch):
    """
    Without qwen_vl_utils the image can never be prepared, so the model would
    score a poster it never saw. The service must return the synthetic fallback
    *without generating* — a flagged blind guess is still a meaningless score —
    and poster_evaluator must store it as FALLBACK with no model attribution.
    """
    import sys

    import ai.vision.qwen_vl_service as qwen_vl
    from app.services.ai.poster_evaluator import poster_evaluator

    monkeypatch.setitem(sys.modules, "qwen_vl_utils", None)  # force ImportError

    class _Processor:
        def apply_chat_template(self, *_args, **_kwargs):
            raise AssertionError("prompt must not be built without vision inputs")

        def __call__(self, *_args, **_kwargs):
            raise AssertionError("model inputs must not be built without an image")

        def batch_decode(self, *_args, **_kwargs):
            raise AssertionError("nothing should be generated to decode")

    class _Model:
        def generate(self, **_kwargs):
            raise AssertionError("the vision model must not run without the image")

    service = qwen_vl.QwenVLService.__new__(qwen_vl.QwenVLService)
    service._processor, service._model = _Processor(), _Model()

    raw = service._run_vision("b64", "image/png", "system", "user")

    assert raw["fallback"] is True
    assert raw["overall_score"] == qwen_vl._FALLBACK_EVAL["overall_score"]
    assert raw is not qwen_vl._FALLBACK_EVAL  # a copy, not the shared constant

    normalized = poster_evaluator.normalize(raw)
    assert normalized["source_type"] == "FALLBACK"
    assert normalized["is_fallback"] is True
    assert normalized["model_name"] is None
