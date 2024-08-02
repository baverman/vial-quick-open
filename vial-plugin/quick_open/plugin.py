import re
import os.path

from collections import defaultdict
from itertools import islice

from vial import vim, vfunc
from vial.fsearch import get_files
from vial.utils import focus_window, get_projects, buffer_with_file, mark, single
from vial.widgets import ListFormatter, ListView, SearchDialog


class NameBuffer:
    def __init__(self, items):
        self.files = {}
        self.names = {}
        self.nbuf = None
        self.unsorted = set()
        self.append(items)

    def merge(self, nb):
        self.nbuf = None

        for k, v in nb.files.items():
            self.files.setdefault(k, []).extend(v)

        self.unsorted.update(nb.names)
        for k, v in nb.names.items():
            self.names.setdefault(k, []).extend(v)

    def append(self, items):
        sd = self.names.setdefault
        added = set()
        for item in items:
            fname = item[1]
            self.files.setdefault(fname, []).append(item)
            parts = fname.split('/')
            c = len(parts)
            for i, p in enumerate(parts, 1):
                added.add(p)
                sd(p, []).append((c - i, c, fname, item))

        self.unsorted.update(added)

    def get_names(self, names):
        to_sort = self.unsorted.intersection(names)
        for r in to_sort:
            self.names[r].sort()
        self.unsorted.difference_update(to_sort)
        return [self.names[r] for r in names]

    def get_matches(self, query):
        if self.nbuf is None:
            self.nbuf = '\n' + '\n'.join(self.names)

        regex = r'(?m)^({0}.*)|(.*{0}.*)$'.format(re.escape(query))
        matches = re.findall(regex, self.nbuf)
        yield self.get_names([r for r, _ in matches if r])
        yield self.get_names([r for _, r in matches if r])

    def get_items(self, fnames):
        result = []
        for it in fnames:
            result.extend(self.files.get(it, []))
        return result


class Searcher:
    def __init__(self, query):
        self.parts = (query or '').replace('//', '/').lstrip('/').split('/')
        self.parts.reverse()
        self.matches = {p: set() for p in self.parts}
        self.ranks = {p: {} for p in self.parts}
        self.order = defaultdict(int)
        self.buffers = []
        self._work_iter = self._work()
        self.done = False

    def _work(self):
        count = 0
        while True:
            if not self.buffers:
                self.done = True
                yield
                continue

            nb = self.buffers.pop()

            for offset, part in enumerate(self.parts):
                empu = self.matches[part].update
                rpe = self.ranks[part]
                for mg in nb.get_matches(part):
                    for m in mg:
                        items = [it for it in m if it[0] >= offset]
                        count += len(m)
                        empu(it[2] for it in items)
                        for it in items:
                            fname = it[2]
                            if fname not in rpe:
                                rpe[fname] = it[0]
                                self.order[fname] += it[0]

                        if count > 100:
                            count = 0
                            yield

    def refine(self, nb):
        self.buffers.append(nb)
        self.done = False

    def result(self, limit=100):
        next(self._work_iter, None)

        f = None
        for part in self.parts:
            d = self.matches.get(part, set())
            if f is None:
                f = d
            else:
                f = f & d

        if len(f) > limit:
            f = list(f)[:limit]

        ordfn = self.order.get
        return sorted(f, key=lambda r: (ordfn(r), r))


class Matcher:
    def __init__(self):
        self.clear()

    def clear(self):
        self.name_buffer = NameBuffer([])
        self.searcher = None

    def set_query(self, query):
        self.searcher = Searcher(query)
        self.searcher.refine(self.name_buffer)

    def append(self, items):
        if not items:
            return
        nb = NameBuffer(items)
        self.name_buffer.merge(nb)
        if self.searcher:
            self.searcher.refine(nb)

    def result(self, limit=100):
        if not self.searcher:
            return []
        fnames = self.searcher.result(limit)
        return self.name_buffer.get_items(fnames)

    @property
    def done(self):
        return self.searcher and self.searcher.done


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

        self.matcher = Matcher()
        self.bmatcher = Matcher()
        self.file_iter_cache = {}

    def open(self):
        self.matcher.clear()
        self.bmatcher.clear()
        self.bmatcher.append(self.get_buffer_paths())
        self.file_iter_cache.clear()
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
            self.bmatcher.set_query(prompt)
            self.matcher.set_query(prompt)
            self.loop.idle(self.fill())
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

    def fill(self):
        current = self.current = object()
        self.list_view.clear()

        bfilelist = [(name, top, fpath, root)
                     for name, _, root, top, fpath
                     in self.bmatcher.result()]
        bfiles = set(r[2] for r in bfilelist)

        for r in self.roots:
            filler = self.get_file_iter(r)
            items = True
            while items or not self.matcher.done:
                if current is not self.current:
                    return
                items = list(islice(filler, 50))
                self.matcher.append(items)
                self.filelist[:] = bfilelist
                result = self.matcher.result()[:20]
                for name, _path, root, top, fpath in result:
                    if fpath not in bfiles:
                        self.filelist.append((name, top, fpath, root))

                self.win.options['statusline'] = f'quick-open: {len(self.matcher.name_buffer.files)}'
                self.list_view.render(True)
                self.loop.refresh()
                yield

        self.list_view.render()


dialog = single(QuickOpen)
def quick_open():
    dialog().open()
