import os.path
import re

from vial import vim, vfunc
from vial.utils import get_var, focus_window
from vial.widgets import ListFormatter, ListView, SearchDialog

from .. import quick_open as module
from . import search

module.dialog = None

IGNORE_DIRS = re.compile(r'(^|.*/)(\.git|\.svn|\.hg)$')
IGNORE_FILES = re.compile(r'^.*(\.pyc|\.pyo|\.swp|\.class|\.o)$')

def quick_open():
    if not module.dialog:
        module.dialog = QuickOpen()

    module.dialog.open()

class QuickOpen(SearchDialog):
    def __init__(self):
        self.filelist = []
        SearchDialog.__init__(self, '__vial_quick_open__', 
            ListView(self.filelist, ListFormatter(0, 0, 1, 1)))

    def open(self):
        self.last_window = vfunc.winnr()
        self.roots = get_var('vial_projects', [os.getcwd()])
        self.list_view.clear()
        self.show(u'')
        self.loop.enter()

    def on_select(self, item, cursor):
        focus_window(self.last_window)
        vim.command('e {}'.format(item[2]))

    def on_cancel(self):
        focus_window(self.last_window)

    def on_prompt_changed(self, prompt):
        if prompt:
            self.loop.idle(self.fill(prompt))
        else:
            self.list_view.show_cursor(False)
            self.buf[0:] = ['Type something to search']
            self.loop.refresh()

    def fill(self, prompt):
        current = self.current = object()
        self.list_view.clear()
        last_index = 0
        cnt = 0
        already_matched = {}

        file_cache = {}
        def fill_cache(seq, cache):
            for r in seq:
                cache.append(r)
                yield r

        for m in search.get_matchers(prompt):
            for r in self.roots:
                if r in file_cache:
                    flist = file_cache[r]
                else:
                    cache = file_cache[r] = []
                    flist = fill_cache(search.get_files(r, '', IGNORE_FILES, IGNORE_DIRS), cache)

                for name, path, root, top, fpath in flist:
                    if current is not self.current:
                        return

                    if fpath not in already_matched and m(name, path):
                        already_matched[fpath] = True

                        self.filelist.append((name, top, fpath, root))
                        if len(self.filelist) > 20:
                            self.list_view.render()
                            return

                    cnt += 1
                    if not cnt % 50:
                        self.list_view.render()
                        self.loop.refresh()
                        yield

            self.list_view.render()

