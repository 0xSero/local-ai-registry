"""Optional runtime checks: python -m pytest -q sources/qwen38-apple-silicon/test_runtime.py.

Requires the pinned runtime and pytest. Uses small synthetic tensors/models only;
these checks do not load the 27B checkpoint or establish hardware qualification.
"""

from pathlib import Path
from types import ModuleType, SimpleNamespace
import pytest
import mlx.core as mx
from mlx_vlm.generate.ar import PromptProcessingBatch

path = Path(__file__).parents[2] / 'registry/asset/qwen38-mlx-vlm-serve.py'
# Registry assets are checksum-addressed inputs; do not generate __pycache__
# beside the wrapper while importing it for these optional runtime checks.
serve = ModuleType('qwen_serve')
serve.__file__ = str(path)
exec(compile(path.read_bytes(), str(path), 'exec'), serve.__dict__)


def test_memory_limit_defaults_and_overrides():
    assert serve.memory_limit_bytes(30 * serve.GIB, None) == 27 * serve.GIB
    assert serve.memory_limit_bytes(18 * serve.GIB, None) == 18 * serve.GIB
    assert serve.memory_limit_bytes(30 * serve.GIB, '20.5') == int(20.5 * serve.GIB)
    for invalid in ('0', '-1', 'nan', 'inf', '30.1', 'bad', '0.00000000001'):
        with pytest.raises(ValueError):
            serve.memory_limit_bytes(30 * serve.GIB, invalid)


def test_runtime_pin_and_private_metadata():
    metadata = serve.runtime_metadata()
    assert metadata['distributions']['mlx-vlm'] == '0.7.3'
    assert metadata['mlx_vlm_source_revision'] == serve.RUNTIME_REVISION
    assert 'url' not in metadata and 'path' not in metadata


def test_audit_does_not_mistake_recurrent_state_for_kv():
    from mlx_vlm.models.cache import ArraysCache, BatchKVCache
    recurrent = ArraysCache(2)
    recurrent.left_padding = mx.array([0])
    recurrent[0], recurrent[1] = mx.zeros((1, 2, 2)), mx.zeros((1, 2, 2))
    kv = BatchKVCache([0])
    kv.update_and_fetch(mx.ones((1, 1, 7, 8)), mx.ones((1, 1, 7, 8)))
    processing = SimpleNamespace(
        _prompt_tokens_per_row=[7], _cached_tokens_per_row=[0], _processed_prompt_columns=6,
        model=SimpleNamespace(model_type='qwen3_5_text', model=SimpleNamespace(
            layers=[SimpleNamespace(is_linear=True), SimpleNamespace(is_linear=False)])),
    )
    generated = SimpleNamespace(prompt_cache=[recurrent, kv], hidden=mx.zeros((1, 1, 8)))
    record = serve.prefill_audit(processing, generated, mx)
    assert record['full_attention_cache_retained'] is True
    assert record['layers'][0]['retained_tokens'] is None
    kv.trim(1)
    failed = serve.prefill_audit(processing, generated, mx)
    assert failed['full_attention_cache_retained'] is False and failed['errors']


def test_hook_preserves_chunked_native_mtp_execution(monkeypatch, capsys):
    original = PromptProcessingBatch.generate
    monkeypatch.setattr(PromptProcessingBatch, 'generate', original)
    serve.install_cache_audit(mx)
    _run_tiny_chunked_mtp()
    output = capsys.readouterr().err
    assert output.count('qwen38_prefill_audit') == 1
    assert '"full_attention_cache_retained": true' in output
    assert '"prompt_tokens_per_row": [9]' in output
    assert '"hidden_shape": [1, 1, 64]' in output


def test_runtime_cache_without_nbytes_does_not_abort_audit():
    from mlx_vlm.models.cache import ArraysCache, BatchQuantizedKVCache
    recurrent = ArraysCache(2)
    recurrent.left_padding = mx.array([0])
    recurrent[0], recurrent[1] = mx.zeros((1, 2, 2)), mx.zeros((1, 2, 2))
    kv = BatchQuantizedKVCache([0], bits=4, group_size=32)
    kv.update_and_fetch(mx.ones((1, 1, 7, 32)), mx.ones((1, 1, 7, 32)))
    processing = SimpleNamespace(
        _prompt_tokens_per_row=[7], _cached_tokens_per_row=[0], _processed_prompt_columns=6,
        model=SimpleNamespace(model_type='qwen3_5_text', model=SimpleNamespace(
            layers=[SimpleNamespace(is_linear=True), SimpleNamespace(is_linear=False)])),
    )
    generated = SimpleNamespace(prompt_cache=[recurrent, kv], hidden=mx.zeros((1, 1, 8)))
    record = serve.prefill_audit(processing, generated, mx)
    assert record['full_attention_cache_retained'] is True
    assert record['full_attention_layers_verified'] == [1]
    assert record['cache_bytes_is_partial'] is True
    assert record['cache_bytes_unknown_layers'] == [1]
    assert record['layers'][1]['cache_bytes'] is None
    assert record['layers'][1]['cache_bytes_unavailable_reason'] == 'nbytes_not_supported'
    assert record['cache_bytes'] == recurrent.nbytes


def _run_tiny_chunked_mtp():
    from mlx_vlm.models.qwen3_5.config import TextConfig
    from mlx_vlm.models.qwen3_5.language import LanguageModel
    from mlx_vlm.speculative.drafters.qwen3_5_mtp import Model, ModelConfig
    from mlx_vlm.models.cache import BatchKVCache
    from mlx_vlm.turboquant import BatchTurboQuantKVCache

    cfg = TextConfig(
        model_type='qwen3_5_text', hidden_size=64, intermediate_size=128,
        linear_num_value_heads=2, linear_num_key_heads=2,
        linear_key_head_dim=4, linear_value_head_dim=4,
        linear_conv_kernel_dim=4, num_hidden_layers=4,
        num_attention_heads=2, rms_norm_eps=1e-6, vocab_size=32,
        num_key_value_heads=1, max_position_embeddings=128,
        tie_word_embeddings=True, head_dim=32, full_attention_interval=2,
        rope_parameters={'type': 'default', 'mrope_section': [1, 0, 0],
                         'rope_theta': 10000, 'partial_rotary_factor': 0.25},
    )
    outer = SimpleNamespace(
        model_type='qwen3_5', text_config=cfg,
        vision_config=SimpleNamespace(spatial_merge_size=2),
        image_token_id=30, video_token_id=29, vision_start_token_id=28,
    )
    mx.random.seed(12)
    model = LanguageModel(cfg, outer)
    cfg.mtp_num_hidden_layers = 1
    drafter = Model(ModelConfig(text_config=cfg, block_size=4))
    tokens = mx.array([[1, 2, 3, 4, 5, 6, 7, 8, 9]])
    batch = PromptProcessingBatch(
        model=model, uids=[1], input_ids=tokens.tolist(), max_tokens=[8],
        inputs_embeds=model.model.embed_tokens(tokens), prompt_kwargs={},
        prefill_step_size=2, draft_model=drafter, draft_kind='mtp',
        kv_bits=4, kv_quant_scheme='turboquant', quantized_kv_start=0,
    )
    while batch.needs_processing():
        assert batch.prompt_step() <= 2
    generated = batch.generate(lambda x: mx.argmax(x, axis=-1), lambda *args: False,
                               compute_logprobs=False)
    assert generated.hidden.shape[1] == 1
    attention = [c for c in generated.prompt_cache
                 if isinstance(c, (BatchKVCache, BatchTurboQuantKVCache))]
    assert any(isinstance(c, BatchTurboQuantKVCache) for c in attention)
    assert all(c._idx == 9 for c in attention)
    responses = []
    while len(generated):
        responses.extend(generated.next())
    assert len(responses) == 8 and drafter.draft_lens
