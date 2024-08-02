import vial
import re

simple_ignored_dirs = [
    'build',
    'dist',
    '__pycache__',
    '.egg-info',
    '.git',
    '.hg',
    '.mypy_cache',
    '.pytest_cache',
    '.idea',
]

def init():
    vial.register_command('VialQuickOpen', '.plugin.quick_open')

    vial.vim.vars['vial_ignore_dirs_default'] = ['^{}$'.format(re.escape(it)) for it in simple_ignored_dirs]

    vial.vim.vars['vial_ignore_extensions_default'] = [
        'pyc', 'pyo', 'swp', 'class', 'o']

