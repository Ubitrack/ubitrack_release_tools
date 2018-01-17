import os
import platform
import re
import sys
from collections import defaultdict
import shutil

from conans.client.conan_api import Conan
from conans.client.runner import ConanRunner
from conans.model.ref import ConanFileReference
from conans.model.version import Version
from conans import __version__ as client_version

class ConanOutputRunner(ConanRunner):

    def __init__(self):
        super(ConanOutputRunner, self).__init__()

        class OutputInternal(object):
            def __init__(self):
                self.output = ""

            def write(self, data):
                self.output += str(data)
                # sys.stdout.write(data)

        self._output = OutputInternal()

    @property
    def output(self):
        return self._output.output

    def __call__(self, command):
        return super(ConanOutputRunner, self).__call__(command, output=self._output)


def parse_depencencies(pkg):
    runner = ConanOutputRunner()
    runner("conan info %s -n url" % pkg)
    lines = [l.strip() for l in runner.output.split("\n")]

    ret = []
    reference = None
    url = None

    for l in lines:
        if "overriden" in l or "Version" in l:
            continue

        try:
            reference = ConanFileReference.loads(l)
            continue
        except:
            url = None

        if l.startswith("URL:"):
            url = [v.strip() for v in l.split(": ")][-1]

        if reference is not None and url is not None:
            ret.append((reference, url))
            reference = None
            url = None

    return ret


if __name__ == '__main__':
    pkg = "ubitrack/1.3.0@ubitrack/stable"
    deps = parse_depencencies(pkg)


    build_folder = "build"
    if os.path.isdir(build_folder):
        shutil.rmtree(build_folder)
    os.mkdir(build_folder)
 
    for ref, url in deps:
        if not ref.user in ['camposs', 'ubitrack']:
            continue

        print("Clone %s" % url)
        pkg_folder = os.path.join(build_folder, ref.name)
        ConanOutputRunner()("git clone %s %s" % (url, pkg_folder))

        print("Export %s" % str(ref))
        ConanOutputRunner()("conan export %s %s/%s" % (pkg_folder, ref.user, ref.channel))
