import os.path
import re

from vial import vim, vfunc
from vial.utils import get_var, focus_window
from vial.widgets import ListFormatter, ListView, SearchDialog

from . import search

IGNORE_DIRS = ['^build$', '^dist$', '(^|.*/)__pycache__$', '.*\.egg-info$', '(^|.*/)\.']
IGNORE_EXTENSIONS = ['pyc', 'pyo', 'swp', 'class', 'o']

dialog = None
def quick_open():
    global dialog
    if not dialog:
        dialog = QuickOpen()

    dialog.open()

class QuickOpen(SearchDialog):
    def __init__(self):
        self.filelist = []
        SearchDialog.__init__(self, '__vial_quick_open__', 
            ListView(self.filelist, ListFormatter(0, 0, 1, 1)))

        self.cache = {}

    def open(self):
        self.cache.clear()
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

    def get_files(self, root):
        try:
            return self.cache[root]
        except KeyError:
            pass

        ignore_files = re.compile('.*({})$'.format('|'.join(r'\.{}'.format(r)
            for r in get_var('vial_ignore_extensions', IGNORE_EXTENSIONS))))

        ignore_dirs = re.compile('({})'.format('|'.join(
            get_var('vial_ignore_dirs', IGNORE_DIRS))))

        cache = []
        def filler():
            for r in search.get_files(root, '', ignore_files, ignore_dirs):
                cache.append(r)
                yield r

            self.cache[root] = cache
        
        return filler()

    def fill(self, prompt):
        current = self.current = object()
        self.list_view.clear()
        last_index = 0
        cnt = 0
        already_matched = {}

        for m in search.get_matchers(prompt):
            for r in self.roots:
                for name, path, root, top, fpath in self.get_files(r):
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

