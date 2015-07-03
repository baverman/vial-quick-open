import re
import os.path

from collections import defaultdict
from itertools import islice
from cStringIO import StringIO

from vial import vim, vfunc
from vial.fsearch import get_files
from vial.utils import focus_window, get_projects, buffer_with_file, mark, single
from vial.widgets import ListFormatter, ListView, SearchDialog


class MatchTree(object):
    def __init__(self):
        self.files = []
        self.names = defaultdict(lambda: defaultdict(list))
        self.nbuf = StringIO()

    def clear(self):
        self.files[:] = []
        self.names.clear()
        self.nbuf.close()
        self.nbuf = StringIO()

    def extend(self, items):
        idx = len(self.files)
        for item in items:
            self.files.append(item)
            parts = item[1].split('/')
            parts.reverse()
            for i, p in enumerate(parts):
                self.names[i][p].append(idx)

            self.nbuf.write('{}/{}\n'.format(idx, parts[0]))
            idx += 1

    def match_name(self, query):
        content = self.nbuf.getvalue()
        if not content:
            return
        regex = r'(?m)^(\d+)/{}'.format(re.escape(query))
        yield [int(m) for m in re.findall(regex, content)]
        regex = r'(?m)^(\d+).*{}.*$'.format(re.escape(query))
        yield [int(m) for m in re.findall(regex, content)]

    def match_part(self, query, level=0):
        if level not in self.names:
            return

        for n, indices in sorted(self.names[level].iteritems()):
            if n.startswith(query):
                yield indices

        for n, indices in sorted(self.names[level].iteritems()):
            if query in n:
                yield indices

    def get_files(self, matcher):
        matched = set()
        files = self.files
        for indices in matcher:
            for idx in (r for r in indices if r not in matched):
                yield files[idx]
            matched.update(indices)

    def match_path(self, query):
        d, _, n = query.rpartition('/')
        def di():
            for level in range(1, 5):
                for r in self.match_part(d, level):
                    yield r

        for item in self.get_files(di()):
            if item[0].startswith(n):
                yield item

        for item in self.get_files(di()):
            if n in item[0] and not item[0].startswith(n):
                yield item

    def match(self, query):
        if '/' in query:
            return self.match_path(query)
        else:
            return self.get_files(self.match_name(query))


def strip_project_path(path, projects, keep_top):
    for p in projects:
        if path.startswith(p + os.sep):
            if keep_top:
                return os.path.join(os.path.basename(p),
                                    path[len(p):].lstrip(os.sep))
            else:
                return path[len(p):].lstrip(os.sep)

    return path


class QuickOpen(SearchDialog):
    def __init__(self):
        self.filelist = []
        SearchDialog.__init__(self, '__vial_quick_open__',
            ListView(self.filelist, ListFormatter(0, 0, 1, 1)), 'quick-open')

        self.matcher = MatchTree()
        self.bmatcher = MatchTree()
        self.file_iter_cache = {}

    def open(self):
        self.matcher.clear()
        self.bmatcher.clear()
        self.file_iter_cache.clear()
        self.bmatcher.extend(self.get_buffer_paths())
        self.last_window = vfunc.winnr()
        self.roots = get_projects()
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
        projects = get_projects()
        multiple_projects = len(projects) > 1
        for b in vim.buffers:
            if buffer_with_file(b):
                fpath = b.name
                spath = strip_project_path(fpath, projects, multiple_projects)
                path, name = os.path.split(spath)
                yield (name, spath, '__buffer__',
                       '* ' + path, fpath)

    def get_file_iter(self, root):
        try:
            return self.file_iter_cache[root]
        except KeyError:
            result = get_files(root, keep_top=len(get_projects()) > 1)
            self.file_iter_cache[root] = result
            return result

    def fill(self, prompt):
        current = self.current = object()
        self.list_view.clear()

        bfilelist = [(name, top, fpath, root)
                     for name, _, root, top, fpath
                     in self.bmatcher.match(prompt)]
        bfiles = set(r[2] for r in bfilelist)

        for r in self.roots:
            filler = self.get_file_iter(r)
            items = True
            while items:
                if current is not self.current:
                    return
                items = list(islice(filler, 50))
                self.matcher.extend(items)
                self.filelist[:] = bfilelist
                result = list(islice(self.matcher.match(prompt), 20))
                for name, _path, root, top, fpath in result:
                    if fpath not in bfiles:
                        self.filelist.append((name, top, fpath, root))

                self.list_view.render(True)
                self.loop.refresh()
                yield

        self.list_view.render()


dialog = single(QuickOpen)
def quick_open():
    dialog().open()
