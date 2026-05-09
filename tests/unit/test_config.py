"""Tests for MinervaConfig loader."""

import os
import tempfile


class TestMinervaConfig:
    """Tests for config loading."""

    def test_load_valid(self):
        """Test loading a minimal valid config."""
        from minerva.config import MinervaConfig

        config = MinervaConfig()

        assert config.llm.provider == "ollama"
        assert config.llm.base_url == "http://localhost:11434/v1"
        assert config.llm.models["agent"] == "qwen3:30b-a3b"
        assert config.execution.monthly_budget_usd == 50.0
        assert config.search.searxng_url == "http://localhost:8080"

    def test_env_override(self):
        """Test environment variable overrides."""
        from minerva.config import MinervaConfig

        os.environ["DEEPSEEK_API_KEY"] = "test-key-123"
        os.environ["OLLAMA_BASE_URL"] = "http://custom:9999/v1"

        config = MinervaConfig()
        config = MinervaConfig._apply_env_overrides(config)

        assert config.cloud.deepseek_api_key == "test-key-123"
        assert config.llm.base_url == "http://custom:9999/v1"

        # Cleanup
        del os.environ["DEEPSEEK_API_KEY"]
        del os.environ["OLLAMA_BASE_URL"]

    def test_load_yaml_file(self):
        """Test loading from a YAML file."""
        from minerva.config import MinervaConfig

        yaml_content = """
tier1:
  llm:
    provider: ollama
    base_url: http://localhost:11434
    models:
      agent: test-model
  knowledge:
    sqlite_path: /tmp/test.db
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            config = MinervaConfig.load(tmp_path)
            assert config.llm.models["agent"] == "test-model"
            assert config.knowledge.sqlite_path == "/tmp/test.db"
        finally:
            os.unlink(tmp_path)
