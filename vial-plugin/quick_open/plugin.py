import re
import os.path

from itertools import islice
from bisect import insort
from heapq import merge

from vial import vim, vfunc
from vial.fsearch import get_files
from vial.utils import focus_window, get_projects, buffer_with_file, mark, single, echom
from vial.widgets import ListFormatter, ListView, SearchDialog


class MatchTree(object):
    def __init__(self):
        self.names = {}
        self.unsorted = set()
        self.nbuf = ''

    def clear(self):
        self.names.clear()
        self.nbuf = ''

    def extend(self, items):
        sd = self.names.setdefault
        for item in items:
            fname = item[1]
            parts = fname.split('/')
            c = len(parts)
            for i, p in enumerate(parts, 1):
                sd(p, []).append((c - i, c, fname, item))

        self.nbuf = '\n'.join(self.names)
        self.unsorted.update(self.names)

    def get_names(self, names):
        to_sort = self.unsorted.intersection(names)
        for r in to_sort:
            self.names[r].sort()
        self.unsorted.difference_update(to_sort)
        return [self.names[r] for r in names]

    def get_matches(self, query):
        if not self.nbuf:
            return
        regex = r'(?m)^({0}.*)|(.*{0}.*)$'.format(re.escape(query))
        matches = re.findall(regex, self.nbuf)
        yield self.get_names([r for r, _ in matches if r])
        yield self.get_names([r for _, r in matches if r])

    def get_files(self, matches):
        matched = set()
        for _, _, fname, item in matches:
            if fname not in matched:
                yield item
                matched.add(fname)

    def filter_idx(self, matches, idx):
        return (r for r in matches if r[0] >= idx)

    def filter_by_stream(self, matches, stream):
        fnames = {}
        for idx, fl, fname, item in matches:
            if fname in fnames:
                yield (fnames[fname], fl, fname, item)
            elif stream:
                for sit in stream:
                    sfname = sit[2]
                    sidx = sit[0]

                    if sidx <= idx:
                        continue

                    fnames.setdefault(sfname, sidx)
                    if fname == sfname:
                        yield sit
                        break
                else:
                    stream = None

    def chain_matches(self, all_matches):
        for matches in all_matches:
            for r in merge(*matches):
                yield r

    def match(self, query):
        parts = (query or '').replace('//', '/').lstrip('/').split('/')
        parts.reverse()
        count = len(parts)
        if count == 1:
            return self.get_files(self.chain_matches(self.get_matches(parts[0])))
        elif count > 1:
            initial = parts[0] and self.chain_matches(self.get_matches(parts[0])) or None
            for offset, part in enumerate(parts[1:], 1):
                stream = self.filter_idx(self.chain_matches(self.get_matches(part)), offset)
                if initial:
                    initial = self.filter_by_stream(initial, stream)
                else:
                    initial = stream
            return self.get_files(initial)
        else:
            return self.get_files([])


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
