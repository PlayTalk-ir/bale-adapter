from pathlib import Path

from bale_platform.secrets_file import append_api_token, active_api_tokens, mask_token, read_api_tokens


def test_mask_token():
    assert mask_token("abcdefghijklmnop") == "abcdef…mnop"


def test_append_api_token(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BALE_SECRETS_FILE", str(tmp_path / ".env.secrets"))
    path = tmp_path / ".env.secrets"
    append_api_token("first_token_1234567890ab", path)
    assert read_api_tokens(path) == ["first_token_1234567890ab"]
    append_api_token("second_token_1234567890ab", path)
    assert read_api_tokens(path) == [
        "first_token_1234567890ab",
        "second_token_1234567890ab",
    ]


def test_active_api_tokens_reloads_after_append(tmp_path: Path, monkeypatch):
    path = tmp_path / ".env.secrets"
    monkeypatch.setenv("BALE_SECRETS_FILE", str(path))
    append_api_token("alpha_token_1234567890ab", path)
    assert active_api_tokens(force=True) == ["alpha_token_1234567890ab"]
    append_api_token("beta_token_1234567890ab", path)
    assert active_api_tokens() == [
        "alpha_token_1234567890ab",
        "beta_token_1234567890ab",
    ]
