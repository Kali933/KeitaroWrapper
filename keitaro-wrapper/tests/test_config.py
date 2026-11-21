from app.config import Settings, get_settings


def test_copy_paste_noise_is_removed_from_key_and_url():
    settings = Settings(keitaro_api_key='  "abc123" ', keitaro_url=" <https://tlgk.host> ", _env_file=None)
    assert settings.keitaro_api_key == "abc123"
    assert settings.keitaro_url == "https://tlgk.host"


def test_env_changes_are_picked_up_without_restart(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)

    env_file.write_text("KEITARO_API_KEY=old-key\n", encoding="utf-8")
    assert Settings(_env_file=env_file).keitaro_api_key == "old-key"
    env_file.write_text("KEITARO_API_KEY=new-key\n", encoding="utf-8")
    assert Settings(_env_file=env_file).keitaro_api_key == "new-key"
    assert callable(get_settings) and not hasattr(get_settings, "cache_info")  # результат не кэшируется
