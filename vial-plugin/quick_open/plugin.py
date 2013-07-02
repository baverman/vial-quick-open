import os.path

from vial import vim, vfunc
from vial.fsearch import get_files, get_matchers
from vial.utils import focus_window, get_projects, buffer_with_file
from vial.widgets import ListFormatter, ListView, SearchDialog

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
        self.cache['__buffer__'] = list(self.get_buffer_paths())
        self.last_window = vfunc.winnr()
        self.roots = ['__buffer__'] + list(get_projects())
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

    def get_buffer_paths(self):
        for b in vim.buffers:
            if buffer_with_file(b):
                fpath = b.name
                path, name = os.path.split(fpath)
                top = '__buffer__'
                yield name, path, '__buffer__', '* ' + path, fpath
                
    def fill(self, prompt):
        current = self.current = object()
        self.list_view.clear()
        last_index = 0
        cnt = 0
        already_matched = {}

        for m in get_matchers(prompt.encode('utf-8')):
            for r in self.roots:
                for name, path, root, top, fpath in get_files(r, self.cache):
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

