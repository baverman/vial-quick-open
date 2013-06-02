import vial
from vial.utils import lfunc

def init():
    vial.register_command('VialQuickOpen', lfunc('.plugin.quick_open'))

