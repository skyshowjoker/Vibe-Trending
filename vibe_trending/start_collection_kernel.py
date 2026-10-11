"""Run an isolated, real JiuwenSwarm AgentServer with collection MCP tools."""
import copy
import os
import signal
import subprocess
from pathlib import Path

import yaml
import certifi

from .agents import DeepSeekAgent


def main():
    root = Path(__file__).resolve().parents[1]
    swarm = Path(os.getenv('VIBE_JIUWENSWARM_ROOT', str(root.parent / 'jiuwenswarm'))).resolve()
    python = Path(os.getenv('VIBE_JIUWENSWARM_PYTHON', str(swarm / '.venv/bin/python')))
    runtime = root / '.runtime/jiuwen-core'
    if not (runtime / 'openjiuwen').exists():
        raise SystemExit('请先安装隔离内核：uv pip install --python ' + str(python) + ' --target ' + str(runtime) + ' --no-deps openjiuwen==0.1.15.post3')
    workspace = root / '.data/jiuwen-collector'
    config_dir = workspace / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    (workspace / 'agent/workspace').mkdir(parents=True, exist_ok=True)
    model = DeepSeekAgent()
    config = yaml.safe_load((swarm / 'jiuwenswarm/resources/config.yaml').read_text())
    config['models']['defaults'] = [{'model_client_config': {
        'api_base': model.base, 'api_key': '${VIBE_DEEPSEEK_API_KEY}', 'model_name': model.model,
        'client_provider': 'OpenAI', 'timeout': 180, 'verify_ssl': True, 'ssl_cert': certifi.where()},
        'model_config_obj': {'temperature': 0}, 'is_default': True, 'alias': 'vibe-deepseek'}]
    config['mcp'] = {'servers': [{'name': 'vibetrending_tools', 'enabled': True,
        'transport': 'streamable-http', 'url': os.getenv('VIBE_COLLECTION_TOOLS_URL', 'http://127.0.0.1:8901') + '/mcp/', 'timeout_s': 90}]}
    config['preferred_language'] = 'zh'
    config['auto_memory_enabled'] = False
    config['memory'] = {'enabled': False}
    config['heartbeat'] = {'enabled': False}
    config['browser'] = {'enabled': False}
    config['hooks'] = {'disable_all_hooks': True}
    config['channels'] = {'web': {'enabled': True}}
    config['permissions'] = {'enabled': False}
    for mode in ('fast', 'plan'):
        config.setdefault('modes', {}).setdefault('agent', {}).setdefault(mode, {})['memory'] = {'enabled': False}
    config_file = config_dir / 'config.yaml'
    config_file.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    config_file.chmod(0o600)
    # The key exists only in process environment, never in generated config files.
    env = copy.copy(os.environ)
    env.update(JIUWENSWARM_DATA_DIR=str(workspace), VIBE_DEEPSEEK_API_KEY=model.key,
               MODEL_NAME=model.model, API_BASE=model.base, API_KEY=model.key, MODEL_PROVIDER='OpenAI')
    env['PYTHONPATH'] = str(runtime) + os.pathsep + str(swarm)
    env['SAFE_CERT_DIR'] = str(Path(certifi.where()).resolve().parent)
    process = subprocess.Popen([str(python), '-m', 'jiuwenswarm.server.app_agentserver', '--port', '18093'], cwd=swarm, env=env)
    def stop(signum, frame):
        if process.poll() is None:
            process.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        raise SystemExit(process.wait())
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)


if __name__ == '__main__':
    main()
