import os
import platform
import re
import sys
from collections import defaultdict
import shutil
import yaml
import argparse
import platform


from conans import __version__ as client_version
from conans.client.conan_api import (Conan, default_manifest_folder)
from conans.errors import ConanException
from conans.model.ref import ConanFileReference
from conans.client.runner import ConanRunner


def main():
    parser = argparse.ArgumentParser(description='Create scripts to assist with making a conan release for ubitrack.')

    parser.add_argument('--config', dest='config', action='store',
                        default="ubitrack-1.3.0.yml",
                        help='yaml config file with the specifcation for the release')

    parser.add_argument('--gitrepo', dest='url', action='store',
                        default="https://github.com/ubitrack/ubitrack",
                        help='url to the git repository for the release-metapackage')

    parser.add_argument('--gitbranch', dest='branch', action='store',
                        default="master",
                        help='url to the git repository for the release-metapackage')

    parser.add_argument('--conanrepo', dest='repo', action='store',
                        default="camp",
                        help='name of the conan repository to use')

    parser.add_argument('--conanuser', dest='user', action='store',
                        default="ubitrack",
                        help='conan user to use for publishing')

    parser.add_argument('--conanchannel', dest='channel', action='store',
                        default="stable",
                        help='conan channel to use for publishing')

    args = parser.parse_args()


    config = yaml.load(open(args.config).read())
    branches = {v['name']: v['branch'] for v in config}

    build_folder = "build"
    meta_repo_folder = os.path.join(build_folder, "meta")

    # clean previous build folder and create a fresh one
    if os.path.isdir(build_folder):
        shutil.rmtree(build_folder)
    os.mkdir(build_folder)

    # first download and export the meta package
    ConanRunner()("git clone --branch master %s %s" % (args.url, meta_repo_folder), output=None)
    ConanRunner()("conan export %s %s/%s" % (meta_repo_folder, args.user, args.channel), output=None)

    try:
        conan_api, client_cache, user_io = Conan.factory()

    except ConanException:  # Error migrating
        sys.exit(-1)

    deps_graph, graph_updates_info, project_reference = conan_api.info_get_graph(meta_repo_folder,
                                                                                 # remote=args.remote,
                                                                                 # settings=args.settings,
                                                                                 # options=args.options,
                                                                                 # env=args.env,
                                                                                 # profile_name=args.profile,
                                                                                 # update=args.update,
                                                                                 # install_folder=args.install_folder
                                                                                 )

    graph_updates_info = graph_updates_info or {}
    all_references = []
    for node in sorted(deps_graph.nodes):
        ref, conan = node
        if not ref:
            # ref is only None iff info is being printed for a project directory, and
            # not a passed in reference
            if project_reference is None:
                continue
            else:
                ref = ConanFileReference.loads("%s@%s/%s" % (project_reference.split("@")[0], args.user, args.channel))

        print (ref.name)
        all_references.append(ref)
        branch = branches.get(ref.name, "master")
        print("Clone %s / %s" % (conan.url, branch))
        pkg_folder = os.path.join(build_folder, ref.name)
        ConanRunner()("git clone --branch %s %s %s" % (branch, conan.url, pkg_folder), output=None)

        print("Export %s" % str(ref))
        ConanRunner()("conan export %s %s/%s" % (pkg_folder, ref.user, ref.channel), output=None)

    # create build_script
    buildscript_lines = ["@echo off"] if platform.system() == "Windows" else []
    buildscript_lines.append('conan create %s %s/%s --build "*"' % (meta_repo_folder, args.user, args.channel))
    for ref in all_references:
        print("Upload %s" % str(ref))
        buildscript_lines.append('conan upload %s -c --all -r %s' % (str(ref), args.repo))


    ext = "bat" if platform.system() == "Windows" else "sh"
    buildscript_fname = "build_release.%s" % ext
    open(buildscript_fname, 'w').write(os.linesep.join(buildscript_lines))
    print("created buildscript: %s" % buildscript_fname)

if __name__ == '__main__':
    main()