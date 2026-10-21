import os,shutil,subprocess,sys,json
from pathlib import Path
import yaml
import pytest
ROOT=Path(__file__).resolve().parents[2]

def test_compose_private_services_and_healthchecks():
    config=yaml.safe_load((ROOT/'compose.yaml').read_text())
    services=config['services']
    assert config['networks']['internal']['internal'] is True
    assert all(not service.get('ports') for name,service in services.items() if name!='proxy')
    assert all(service.get('healthcheck') for name,service in services.items() if name!='migrate')
    assert all(service.get('mem_limit') for service in services.values())
    assert services['db']['user']=='postgres'
    assert 'backup' in services and services['backup']['volumes']==['backup_data:/backups']
    for path in ['backend/Dockerfile','frontend/Dockerfile','ops/proxy/Dockerfile','ops/ollama/Dockerfile','ops/backup/Dockerfile']:
        assert 'USER ' in (ROOT/path).read_text()

def test_setup_and_preflight_do_not_print_or_overwrite_secrets(tmp_path):
    (tmp_path/'ops').mkdir()
    for filename in ['setup.py','check-config.py']:shutil.copy(ROOT/'ops'/filename,tmp_path/'ops'/filename)
    shutil.copy(ROOT/'.env.example',tmp_path/'.env.example')
    result=subprocess.run([sys.executable,str(tmp_path/'ops/setup.py'),'--domain','watch.example.mn'],capture_output=True,text=True)
    assert result.returncode==0
    content=(tmp_path/'.env').read_text()
    assert 'CHANGE_ME' not in content
    if os.name!='posix':pytest.skip('Unix .env permission bits are enforced on Linux CI')
    assert (tmp_path/'.env').stat().st_mode&0o777==0o600
    secret=next(line.split('=',1)[1] for line in content.splitlines() if line.startswith('ADMIN_TOKEN='))
    assert secret not in result.stdout+result.stderr
    again=subprocess.run([sys.executable,str(tmp_path/'ops/setup.py'),'--domain','watch.example.mn'],capture_output=True)
    assert again.returncode!=0 and (tmp_path/'.env').read_text()==content
    checked=subprocess.run([sys.executable,str(tmp_path/'ops/check-config.py')],capture_output=True,text=True)
    assert checked.returncode==0 and secret not in checked.stdout+checked.stderr
    (tmp_path/'.env').chmod(0o644)
    assert subprocess.run([sys.executable,str(tmp_path/'ops/check-config.py')],capture_output=True).returncode!=0

def test_shell_scripts_parse_and_logs_are_valid_json():
    for file in [*ROOT.glob('ops/*.sh'),*ROOT.glob('ops/backup/*.sh')]:
        assert subprocess.run(['sh','-n',str(file)],capture_output=True).returncode==0
    import logging
    from app.log import JsonFormatter
    record=logging.LogRecord('test',logging.INFO,'x',1,'Quotes " and newline\n are safe',(),None)
    assert json.loads(JsonFormatter().format(record))['level']=='INFO'
