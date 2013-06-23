import vial
from vial.utils import lfunc

def init():
    vial.register_command('VialQuickOpen', lfunc('.plugin.quick_open'))

    vial.vim.vars['vial_ignore_dirs_default'] = ['^build$', '^dist$',
        '(^|.*/)__pycache__$', '.*\.egg-info$', '(^|.*/)\.']

    vial.vim.vars['vial_ignore_extensions_default'] = [
        'pyc', 'pyo', 'swp', 'class', 'o']

