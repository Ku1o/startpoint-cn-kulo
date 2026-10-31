"""Repository tools and external state for the later cumulative iOS repairs."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import input_config as cfg
REPO = cfg.REPO


def client():
    """Keep legacy artifact names inside the configured external work directory."""
    return cfg.work('followups')


def private(key):
    result = Path(cfg.path(key))
    if key == 'followup_public_ipa':
        cfg.require_sha(result, 'f4e08c4e5a65de080ca323eaaa35c6a0af90280bf942edcfab050d73f84d3bd8')
    elif key in ('followup_public_verification', 'followup_party_input_record'):
        row = cfg.configuration()['ios'][key]
        if not isinstance(row, dict) or len(row.get('sha256', '')) != 64:
            raise ValueError('Explicit private receipt SHA required: ' + key)
    return result


def tool(relative):
    return Path(cfg.local(relative))


def bootstrap():
    cfg.bind_tools()
    # These are source directories; historical sibling directories hold data only.
    for relative in ('repairs/scripts', 'settings/recipe', 'support/process'):
        value = str(tool(relative))
        if value not in sys.path:
            sys.path.insert(0, value)


def require_bounded_job(seconds=180):
    sys.path.insert(0, str(tool('support/process')))
    from job_guard import require_bounded_job as guard
    return guard(seconds)
