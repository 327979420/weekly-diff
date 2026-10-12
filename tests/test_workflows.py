"""Offline checks for workflow safety and the owner-facing automation contract."""
from pathlib import Path
import re
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / '.github' / 'workflows'
PAUSE_GUARD = "github.event_name != 'schedule' || steps.status.outputs.paused != 'true'"


@pytest.fixture
def workflows() -> dict[str, Any]:
    # BaseLoader preserves GitHub's `on` key (a boolean in YAML 1.1).
    return {path.stem: yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            for path in WORKFLOWS.glob('*.yml')}


def step_named(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job['steps'] if step.get('name') == name)


def action_step(job: dict[str, Any], action: str) -> dict[str, Any]:
    return next(step for step in job['steps']
                if step.get('uses', '').startswith(f'actions/{action}@'))


@pytest.mark.parametrize(('name', 'cron'), [('weekly', '0 21 * * 0'), ('preview', '0 9 * * 5')])
def test_schedules_and_manual_defaults(workflows: dict[str, Any], name: str, cron: str) -> None:
    events = workflows[name]['on']
    assert events['schedule'] == [{'cron': cron}]
    option = events['workflow_dispatch']['inputs']['dry_run']
    assert option['type'] == 'boolean'
    assert option['default'] == 'true'


@pytest.mark.parametrize('name', ['ci', 'weekly', 'preview', 'pages'])
def test_official_actions_and_python(workflows: dict[str, Any], name: str) -> None:
    majors = {'checkout': '7', 'setup-python': '7', 'upload-artifact': '7',
              'download-artifact': '8', 'upload-pages-artifact': '5', 'deploy-pages': '5'}
    for job in workflows[name]['jobs'].values():
        assert job['runs-on'] == 'ubuntu-latest'
        for step in job['steps']:
            if 'uses' in step:
                match = re.fullmatch(r'actions/([a-z-]+)@v(\d+)', step['uses'])
                assert match and majors[match[1]] == match[2]
            if step.get('uses', '').startswith('actions/setup-python@'):
                assert step['with'] == {'python-version': '3.12', 'cache': 'pip'}
            assert 'set -x' not in step.get('run', '')


def test_ci(workflows: dict[str, Any]) -> None:
    ci = workflows['ci']
    assert set(ci['on']) == {'push', 'pull_request'}
    commands = [step.get('run') for step in ci['jobs']['test']['steps']]
    assert 'python -m pip install -r requirements-dev.txt' in commands
    assert 'python -m pytest -q' in commands


def test_least_privilege(workflows: dict[str, Any]) -> None:
    expected = {
        'ci': {'test': {'contents': 'read'}},
        'weekly': {'build': {'contents': 'write'},
                   'deploy': {'pages': 'write', 'id-token': 'write'},
                   'publish': {'contents': 'read'}},
        'preview': {'preview': {'contents': 'read'}},
        'pages': {'build': {'contents': 'read'},
                  'deploy': {'pages': 'write', 'id-token': 'write'}},
    }
    for name, permissions in expected.items():
        assert workflows[name]['permissions'] == {}
        assert {key: job['permissions'] for key, job in workflows[name]['jobs'].items()} == permissions


@pytest.mark.parametrize(('name', 'job_name'), [('weekly', 'build'), ('preview', 'preview')])
def test_paused_schedules_skip_every_subsequent_step(workflows: dict[str, Any], name: str, job_name: str) -> None:
    steps = workflows[name]['jobs'][job_name]['steps']
    status_index = next(i for i, step in enumerate(steps) if step.get('id') == 'status')
    assert steps[status_index]['run'] == 'python run.py status --github-output'
    for step in steps[status_index + 1:]:
        assert PAUSE_GUARD in step['if']
    if name == 'weekly':
        job = workflows[name]['jobs']['build']
        assert PAUSE_GUARD in job['outputs']['active']
        assert "needs.build.outputs.active == 'true'" in workflows[name]['jobs']['deploy']['if']


def test_secrets_are_scoped_to_their_steps(workflows: dict[str, Any]) -> None:
    for workflow in workflows.values():
        assert 'secrets.' not in str(workflow.get('env', {}))
        for job in workflow['jobs'].values():
            assert 'secrets.' not in str({key: value for key, value in job.items() if key != 'steps'})
            for step in job['steps']:
                env = step.get('env', {})
                rest = str({key: value for key, value in step.items() if key != 'env'})
                assert 'secrets.' not in rest
                for key, value in env.items():
                    if 'secrets.' not in value:
                        continue
                    assert value == '${{ secrets.' + key + ' }}'
                    if key.startswith('DISCORD_'):
                        assert 'python run.py publish' in step['run']
                    else:
                        assert key in {'GITHUB_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'}
                        assert 'python run.py build' in step['run']


def test_weekly_dry_run_and_real_artifacts(workflows: dict[str, Any]) -> None:
    job = workflows['weekly']['jobs']['build']
    build = step_named(job, 'Collect and build')
    assert build['env']['DRY_RUN'] == '${{ inputs.dry_run || false }}'
    assert 'flags+=(--dry-run)' in build['run']
    assert 'python run.py collect "${flags[@]}"' in build['run']
    assert 'python run.py build --issue "$ISSUE_ID" "${flags[@]}"' in build['run']
    for name in ['Commit issue data', 'Upload Pages site', 'Upload issue for publishing']:
        assert step_named(job, name)['if'].endswith('&& !inputs.dry_run')
    preview = step_named(job, 'Upload dry run preview')
    assert preview['if'].endswith('&& inputs.dry_run')
    assert preview['with']['name'] == 'site-preview'
    assert preview['with']['path'].splitlines() == [
        'site/', 'build/dry-run/${{ steps.status.outputs.issue_id }}.json']
    assert preview['with']['if-no-files-found'] == 'error'
    commit = step_named(job, 'Commit issue data')['run']
    assert 'git add data/' in commit
    assert 'git diff --cached --quiet' in commit
    assert 'github-actions[bot]' in commit
    assert 'commit -m "Issue $ISSUE_ID"' in commit
    assert 'git push' in commit


def test_publish_waits_for_deploy_and_uses_built_issue(workflows: dict[str, Any]) -> None:
    jobs = workflows['weekly']['jobs']
    assert jobs['deploy']['needs'] == 'build'
    assert '!inputs.dry_run' in jobs['deploy']['if']
    assert set(jobs['publish']['needs']) == {'build', 'deploy'}
    assert 'if' not in jobs['publish']  # Default success gate must not become always().
    upload = step_named(jobs['build'], 'Upload issue for publishing')['with']
    download = action_step(jobs['publish'], 'download-artifact')['with']
    assert upload['name'] == download['name']
    assert upload['path'] == 'data/issues/${{ steps.status.outputs.issue_id }}.json'
    assert download['path'] == 'data/issues/'
    assert jobs['build']['outputs']['issue_id'] == '${{ steps.status.outputs.issue_id }}'
    publish = step_named(jobs['publish'], 'Publish to Discord')
    assert publish['env']['ISSUE_ID'] == '${{ needs.build.outputs.issue_id }}'
    assert publish['run'] == 'python run.py publish --issue "$ISSUE_ID"'
    assert list(jobs['publish']['steps']).index(action_step(jobs['publish'], 'download-artifact')) < jobs['publish']['steps'].index(publish)


def test_preview_never_commits_or_deploys(workflows: dict[str, Any]) -> None:
    job = workflows['preview']['jobs']['preview']
    text = str(job)
    assert 'git push' not in text and 'git commit' not in text
    assert 'actions/deploy-pages' not in text and 'actions/upload-pages-artifact' not in text
    build = step_named(job, 'Collect and build')
    assert '--dry-run' not in build['run']
    publish = step_named(job, 'Publish private preview')
    assert 'python run.py publish --preview --issue "$ISSUE_ID" "${flags[@]}"' in publish['run']
    assert 'flags+=(--dry-run)' in publish['run']
    assert publish['env']['DRY_RUN'] == '${{ inputs.dry_run || false }}'
    assert 'DISCORD_WEBHOOK_URL' not in text
    assert step_named(job, 'Upload preview site')['with']['name'] == 'site-preview'


def test_pages_events_and_render_only(workflows: dict[str, Any]) -> None:
    pages = workflows['pages']
    assert pages['on']['push']['branches'] == ['main']
    assert set(pages['on']['push']['paths']) == {
        'templates/**', 'static/**', 'config.yaml', 'data/issues/**', 'weekly_diff/site.py'}
    assert 'workflow_dispatch' in pages['on']
    commands = [step.get('run', '') for step in pages['jobs']['build']['steps']]
    assert 'python run.py render' in commands
    assert not any('run.py build' in command or 'run.py collect' in command for command in commands)
    assert pages['jobs']['deploy']['needs'] == 'build'


def test_pages_deployment_and_shared_concurrency(workflows: dict[str, Any]) -> None:
    assert workflows['weekly']['concurrency'] == {'group': 'weekly-diff', 'cancel-in-progress': 'false'}
    assert workflows['pages']['concurrency'] == workflows['weekly']['jobs']['deploy']['concurrency'] == {
        'group': 'pages', 'cancel-in-progress': 'false'}
    for name in ('weekly', 'pages'):
        jobs = workflows[name]['jobs']
        assert action_step(jobs['build'], 'upload-pages-artifact')['with']['path'] == 'site/'
        deploy = jobs['deploy']
        assert deploy['environment'] == {'name': 'github-pages', 'url': '${{ steps.deployment.outputs.page_url }}'}
        assert action_step(deploy, 'deploy-pages')['id'] == 'deployment'
