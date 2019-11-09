from conans.client.command import main
import os
import sys
from collections import OrderedDict

import conans
from conans import __version__ as client_version
from conans.client import packager, tools
from conans.client.cache.cache import ClientCache
from conans.client.cmd.build import cmd_build
from conans.client.cmd.create import create
from conans.client.cmd.download import download
from conans.client.cmd.export import cmd_export, export_alias
from conans.client.cmd.export_pkg import export_pkg
from conans.client.cmd.profile import (cmd_profile_create, cmd_profile_delete_key, cmd_profile_get,
                                       cmd_profile_list, cmd_profile_update)
from conans.client.cmd.search import Search
from conans.client.cmd.uploader import CmdUpload
from conans.client.cmd.user import user_set, users_clean, users_list
from conans.client.conf import ConanClientConfigParser
from conans.client.graph.graph import RECIPE_EDITABLE
from conans.client.graph.graph_manager import GraphManager
from conans.client.graph.printer import print_graph
from conans.client.graph.proxy import ConanProxy
from conans.client.graph.python_requires import ConanPythonRequire
from conans.client.graph.range_resolver import RangeResolver
from conans.client.hook_manager import HookManager
from conans.client.importer import run_imports, undo_imports
from conans.client.installer import BinaryInstaller
from conans.client.loader import ConanFileLoader
from conans.client.migrations import ClientMigrator
from conans.client.output import ConanOutput, colorama_initialize
from conans.client.profile_loader import profile_from_args, read_profile
from conans.client.recorder.action_recorder import ActionRecorder
from conans.client.recorder.search_recorder import SearchRecorder
from conans.client.recorder.upload_recoder import UploadRecorder
from conans.client.remote_manager import RemoteManager
from conans.client.remover import ConanRemover
from conans.client.rest.auth_manager import ConanApiAuthManager
from conans.client.rest.conan_requester import ConanRequester
from conans.client.rest.rest_client import RestApiClient
from conans.client.runner import ConanRunner
from conans.client.source import config_source_local
from conans.client.store.localdb import LocalDB
from conans.client.userio import UserIO
from conans.errors import (ConanException, RecipeNotFoundException,
                           PackageNotFoundException, NoRestV2Available, NotFoundException)
from conans.model.conan_file import get_env_context_manager
from conans.model.editable_layout import get_editable_abs_path
from conans.model.graph_info import GraphInfo, GRAPH_INFO_FILE
from conans.model.ref import ConanFileReference, PackageReference, check_valid_ref
from conans.model.version import Version
from conans.model.workspace import Workspace
from conans.paths import BUILD_INFO, CONANINFO, get_conan_user_home
from conans.search.search import search_recipes
from conans.tools import set_global_instances
from conans.unicode import get_cwd
from conans.util.files import exception_message_safe, mkdir, save_files
from conans.util.log import configure_logger
from conans.util.tracer import log_command, log_exception

from collections import OrderedDict

import yaml

from conans.client.graph.graph import RECIPE_EDITABLE
from conans.errors import ConanException
from conans.model.editable_layout import get_editable_abs_path, EditableLayout
from conans.model.ref import ConanFileReference
from conans.util.files import load, save

import conans.client.cmd.build as _build

from conans.client.conan_api import get_graph_info


def workspace_install(self, path, settings=None, options=None, env=None,
                          remote_name=None, build=None, profile_name=None,
                          update=False, cwd=None, install_folder=None):
        cwd = cwd or get_cwd()
        abs_path = os.path.normpath(os.path.join(cwd, path))

        remotes = self.app.load_remotes(remote_name=remote_name, update=update)
        # remotes = self.app.cache.registry.load_remotes()
        # remotes.select(remote_name)
        # self.app.python_requires.enable_remotes(update=update, remotes=remotes)

        workspace = Workspace(abs_path, self.app.cache)
        graph_info = get_graph_info(profile_name, settings, options, env, cwd, None,
                                    self.app.cache, self.app.out)

        self.app.out.info("Configuration:")
        self.app.out.writeln(graph_info.profile_host.dumps())

        self.app.cache.editable_packages.override(workspace.get_editable_dict())

        recorder = ActionRecorder()
        deps_graph = self.app.graph_manager.load_graph(workspace.root, None, graph_info, build,
                                                       False, update, remotes, recorder)

        print_graph(deps_graph, self.app.out)

        # Inject the generators before installing
        for node in deps_graph.nodes:
            if node.recipe == RECIPE_EDITABLE:
                generators = workspace[node.ref].generators
                if generators is not None:
                    tmp = list(node.conanfile.generators)
                    tmp.extend([g for g in generators if g not in tmp])
                    node.conanfile.generators = tmp

        installer = BinaryInstaller(self.app, recorder)
        installer.install(deps_graph, remotes, build, update, keep_build=False, graph_info=graph_info)

        install_folder = install_folder or cwd
        workspace.generate(install_folder, deps_graph, self.app.out)

        workspace.build(install_folder, deps_graph, self.app.out,self.app)


def build(self, install_folder, graph, output, app):        
        if self._ws_generator == "cmake":
            cmake = ""
            add_subdirs = ""
            # To avoid multiple additions (can happen for build_requires repeated nodes)
            unique_refs = OrderedDict()
            for node in graph.ordered_iterate():
                if node.recipe != RECIPE_EDITABLE:
                    continue
                unique_refs[node.ref] = node
            
           
            for ref, node in unique_refs.items():
                ws_pkg = self._workspace_packages[ref]
                layout = self._cache.package_layout(ref)
                editable = layout.editable_cpp_info()

                conanfile = node.conanfile
                src = build = None
                if editable:
                    build = editable.folder(ref, EditableLayout.BUILD_FOLDER, conanfile.settings,
                                            conanfile.options)
                    src = editable.folder(ref, EditableLayout.SOURCE_FOLDER, conanfile.settings,
                                          conanfile.options)
                    

                    build = os.path.join(ws_pkg.root_folder, build).replace("\\", "/")
                    src = os.path.join(ws_pkg.root_folder, src).replace("\\", "/")
                    package_folder = os.path.join(build, 'package').replace("\\", "/")
                    
                    conanFilePath = os.path.join(ws_pkg.root_folder, src, "conanfile.py").replace("\\", "/")
                    #print("install folder "+install_folder)
                    #print("build folder "+build)
                    #build(graph_manager, hook_manager, conanfile_path, source_folder, build_folder, package_folder, install_folder,
                    #test=False, should_configure=True, should_build=True, should_install=True, should_test=True)
                    #build(app, conanfile_path, source_folder, build_folder, package_folder, install_folder,
                    #test=False, should_configure=True, should_build=True, should_install=True, should_test=True):
                    _build.cmd_build(app,conanFilePath,src,build, install_folder, build)



myconan_api = sys.modules['conans.client.conan_api']
myconan_api.ConanAPIV1.workspace_install = workspace_install
sys.modules['conans.client.conan_api'] = myconan_api

myworkspace = sys.modules['conans.model.workspace']
myworkspace.Workspace.build = build
sys.modules['conans.model.workspace'] = myworkspace

def run():
    main(sys.argv[1:])


if __name__ == '__main__':
    run()