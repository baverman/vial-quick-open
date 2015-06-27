import os.path
from collections import defaultdict
from itertools import islice

from vial import vim, vfunc
from vial.fsearch import get_files
from vial.utils import focus_window, get_projects, buffer_with_file, mark, single
from vial.widgets import ListFormatter, ListView, SearchDialog


class MatchTree(object):
    def __init__(self):
        self.files = []
        self.names = defaultdict(lambda: defaultdict(set))
        self.parts = []

    def clear(self):
        self.files[:] = []
        self.names.clear()
        self.parts[:] = []

    def extend(self, items):
        idx = len(self.files)
        for item in items:
            self.files.append(item)
            parts = item[1].split('/')
            parts.reverse()
            self.parts.append(parts)
            for i, p in enumerate(parts):
                self.names[i][p].add(idx)
            idx += 1

    def match_name(self, query):
        for n, indices in self.names[0].iteritems():
            if n.startswith(query):
                yield indices

        for n, indices in self.names[0].iteritems():
            if query in n:
                yield indices

    def get_files(self, matcher):
        matched = set()
        files = self.files
        for indices in matcher:
            for idx in indices - matched:
                yield files[idx]
            matched.update(indices)

    def get_indexes(self, matcher):
        matched = set()
        files = self.files
        for indices in matcher:
            for idx in indices - matched:
                yield idx
            matched.update(indices)

    def match_path(self, query):
        d, _, n = query.rpartition('/')
        parts = self.parts
        for level in range(1, 5):
            for idx in self.get_indexes(self.match_name(n)):
                try:
                    part = parts[idx][level]
                except IndexError:
                    continue
                if part.startswith(d):
                    yield set((idx,))

        for level in range(1, 5):
            for idx in self.get_indexes(self.match_name(n)):
                try:
                    part = parts[idx][level]
                except IndexError:
                    continue
                if d in part:
                    yield set((idx,))

    def match(self, query):
        if '/' in query:
            return self.get_files(self.match_path(query))
        else:
            return self.get_files(self.match_name(query))


class QuickOpen(SearchDialog):
    def __init__(self):
        self.filelist = []
        SearchDialog.__init__(self, '__vial_quick_open__',
            ListView(self.filelist, ListFormatter(0, 0, 1, 1)), 'quick-open')

        self.matcher = MatchTree()
        self.file_iter_cache = {}

    def open(self):
        self.matcher.clear()
        self.file_iter_cache.clear()
        self.matcher.extend(self.get_buffer_paths())
        self.last_window = vfunc.winnr()
        self.roots = ['__buffer__'] + list(get_projects())
        self.list_view.clear()
        self.show(u'')
        self.loop.enter()

    def on_select(self, item, cursor):
        focus_window(self.last_window)
        mark()
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

    def get_file_iter(self, root):
        try:
            return self.file_iter_cache[root]
        except KeyError:
            result = self.file_iter_cache[root] = get_files(root)
            return result

    def fill(self, prompt):
        current = self.current = object()
        self.list_view.clear()

        for r in self.roots:
            filler = self.get_file_iter(r)
            items = True
            while items:
                if current is not self.current:
                    return
                items = list(islice(filler, 50))
                self.matcher.extend(items)
                self.filelist[:] = []
                result = list(islice(self.matcher.match(prompt), 20))
                for name, _path, root, top, fpath in result:
                    self.filelist.append((name, top, fpath, root))

                self.list_view.render(True)
                self.loop.refresh()
                yield

        self.list_view.render()


dialog = single(QuickOpen)
def quick_open():
    dialog().open()
