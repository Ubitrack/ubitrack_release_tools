#! /usr/bin/env python3

import os
import sys
import yaml
import shutil
import platform
import semver
from fnmatch import fnmatch

from doit.tools import result_dep
from doit import create_after, get_var

from conans import __version__ as client_version
from conans.client.conan_api import (Conan, default_manifest_folder)
from conans.errors import ConanException
from conans.model.ref import ConanFileReference
from conans.client.tools import Git as ConanGit
from conans.client.runner import ConanRunner

import workspace.ubitrackWorkspace


if not semver.gte(client_version, '1.20.0', True):
    raise RuntimeError("Please upgrade your conan to version >=1.20.0")


BUILD_CONFIG_NAME = os.path.join(os.curdir, "build_config.yml")
SKIP_PACKAGES = ["cmake_installer", ]

# this should be configurable in build_spec
if platform.system().startswith("Darwin"):
    SKIP_PACKAGES.append("cuda_dev_config")
    SKIP_PACKAGES.append("nvpipe")

#
# These are commandline variables that are specified as follows:
# doit varname=value varname=value ...
#
global_config = {"build_spec": get_var("build_spec", "default_build.yml"),
                 "build_folder": get_var("build_folder", "build"),
                 "upload": get_var("upload", "false").lower() == "true",
                 "profile_name": get_var("profile_name", "default"),
                 "workspace": get_var("workspace", "false").lower() == "true",
                 "deps_build_filter": get_var("deps_build_filter", "*"),
                 }


class Git(ConanGit):

    def update(self):
        if os.path.exists(self.folder):
            output = self.run("pull")
            return output
        else:
            raise ConanException("The destination folder '%s' is not empty, "
                                 "specify a branch to checkout (not a tag or commit) "
                                 "or specify a 'subfolder' "
                                 "attribute in the 'scm'" % self.folder)


################################
#
#
#
################################
def load_config(config, build_folder):
    print("Loading configuration from: %s" % config)
    data = yaml.load(open(config).read())
    # use os.curdir if not an absolute path ?
    meta_repo_folder = os.path.join(build_folder, "meta")
    profile_folder = data['config']['profile_directory']

    dependencies = []
    for fname in data['profiles']:
        print("Loading profile: %s" % fname)
        ddata = yaml.load(open(os.path.join(profile_folder, fname)).read())
        dependencies.extend(ddata.get('dependencies', []))
    data["dependencies"] = dependencies

    build_config = {
        "meta_repo_folder": meta_repo_folder,
        "dependencies": dependencies,
        "name": data["meta_package"]["name"],
        "version": data["meta_package"]["version"],
        "user": data["meta_package"]["user"],
        "channel": data["meta_package"]["channel"],
        }
    yaml.dump(build_config, open(BUILD_CONFIG_NAME, "w"))

    return {"config": data,
            "meta_repo_folder": meta_repo_folder,
            }


def task_load_config():
    return {'actions': [(load_config,[global_config["build_spec"], global_config["build_folder"],])],
            'verbosity': 2,
            }


################################
#
#
#
################################
def prepare_meta_repository(meta_repo_folder, config, wipe):
    if wipe and os.path.exists(meta_repo_folder):
        print("Removing meta-repo folder: %s" % meta_repo_folder)
        shutil.rmtree(meta_repo_folder)

    scm = Git(folder=meta_repo_folder)

    gitrepo = config['meta_package']['gitrepo']
    gitbranch = config['meta_package']['gitbranch']

    if os.path.exists(meta_repo_folder) and os.listdir(meta_repo_folder):
        print("Updating meta-repository: %s - %s" % (gitrepo, gitbranch))
        out = scm.update()
        print("Updated meta-repository.\n %s" % out)
    else:
        print("Cloning meta-repository: %s - %s" % (gitrepo, gitbranch))
        out = scm.clone(gitrepo, branch=gitbranch)
        print("Cloned meta-repository.\n %s" % out)
    return {
        "commit_rev": scm.get_commit(),
        "meta_repo_folder": meta_repo_folder,
    }


################################
#
#
#
################################
def export_meta_package(meta_repo_folder, meta_commit_rev, config):
    name = config['meta_package']['name']
    version = config['meta_package']['version']
    user = config['meta_package']['user']
    channel = config['meta_package']['channel']
    conan_api, client_cache, user_io = Conan.factory()

    conan_api.export(meta_repo_folder, name=name, channel=channel, version=version, user=user)


    try:
        conan_file_loc = os.path.join(meta_repo_folder, "conanfile.py")
        version = conan_api.inspect(conan_file_loc, attributes=['version'])['version']
    except ConanException as e:
        print("error retrieving version from package: %s" % str(e))

    return {
        "commit_rev": meta_commit_rev,
        "meta_repo_folder": meta_repo_folder,
        "name": name,
        "version": version,
        "user": user,
        "channel": channel,
        }


################################
#
#
#
################################
def prepare_package_repository(name, gitrepo, gitbranch, build_folder, config, wipe):
    package_repo_folder = os.path.join(build_folder, name)
    if wipe and os.path.exists(package_repo_folder):
        print("Removing pacakge-repo folder: %s" % package_repo_folder)
        shutil.rmtree(package_repo_folder)

    scm = Git(folder=package_repo_folder)
    if os.path.exists(package_repo_folder) and os.listdir(package_repo_folder):
        if not global_config["workspace"]:
            print("Updating package-repository: %s - %s" % (gitrepo, gitbranch))
            out = scm.update()
            print("Updated package-repository.\n %s" % out)
        else:
            print("Local Workspace build, not updating from git: %s - %s" % (gitrepo, gitbranch))
    else:
        print("Cloning package-repository: %s - %s" % (gitrepo, gitbranch))
        out = scm.clone(gitrepo, branch=gitbranch)
        print("Cloned package-repository.\n %s" % out)

    package_commit_rev = scm.get_commit()

    return {
        "name": name,
        "commit_rev": package_commit_rev,
        "package_repo_folder": package_repo_folder,
    }


################################
#
#
#
################################
def export_package(user, channel, name, package_repo_folder, package_commit_rev):
    conan_api, client_cache, user_io = Conan.factory()

    try:
        _, project_reference = conan_api.info(package_repo_folder)
        version = project_reference.version
    except:
        raise ValueError("missing conan version for: %s" % name)

    conan_api.export(package_repo_folder, name=name, channel=channel, version=version, user=user)

    try:
        conan_file_loc = os.path.join(package_repo_folder, "conanfile.py")
        version = conan_api.inspect(conan_file_loc, attributes=['version'])['version']
    except ConanException as e:
        print("error retrieving version from package: %s" % str(e))

    return {
        "commit_rev": package_commit_rev,
        "package_repo_folder": package_repo_folder,
        "name": name,
        "version": version,
        "user": user,
        "channel": channel,
        }


################################
#
#
#
################################
def upload_package(name, version, user, channel, package_commit_rev, config):
    if global_config["upload"]:
        conan_api, client_cache, user_io = Conan.factory()
        conan_repo = {v['name']: v['conanuser'] for v in config['dependencies']}

        ref = "%s/%s@%s/%s" % (name, version, user, channel)
        remote = conan_repo[name]
        if remote is not None:
            result = conan_api.upload(ref, confirm=True, remote_name=remote, policy="force-upload")
    else:
        print("Upload of packages sources is disabled: %s" % name)
    
    return {
        "commit_rev": package_commit_rev,
        "name": name,
        "version": version,
        "user": user,
        "channel": channel,
        }


################################
#
#
#
################################
def build_release(deps, build_folder, config):
    name = config['meta_package']['name']
    version = config['meta_package']['version']
    user = config['meta_package']['user']
    channel = config['meta_package']['channel']

    profile_name = global_config['profile_name']

    package_repo_folder = os.path.join(build_folder, "meta")

    deps_build_filter = global_config.get('deps_build_filter', '*')

    build_modes = [name,] + [d for d in deps if fnmatch(d, deps_build_filter)]

    options = config.get('options', [])

    conan_api, client_cache, user_io = Conan.factory()

    kw = {
    "name": name,
    "version": version,
    "user": user,
    "channel": channel,
    "build_modes": build_modes,
    "options": options}
    kw["profile_names"] = [profile_name,] if profile_name is not None else []

    result = conan_api.create(package_repo_folder, **kw)

    packages = []
    for info in result['installed']:
        packages.append({"reference": info['recipe']['id'],
                         "timestamp": info['recipe']['time'].isoformat(),
                         "package_ids": [p['id'] for p in info['packages']],
                         })
    return {'packages': packages}


################################
#
#
#
################################
def deploy_release(packages, config):
    if global_config["upload"]:
        conan_api, client_cache, user_io = Conan.factory()
        conan_repo = {v['name']: v['conanuser'] for v in config['dependencies']}

        for package in packages:
            reference = ConanFileReference.loads(package['reference'])
            if reference.name not in conan_repo:
                print("skip uploading due to missing remote: %s" % str(reference))
                continue
            remote = conan_repo[reference.name]
            all_success = True
            for pid in package['package_ids']:
                try:
                    result = conan_api.upload(package['reference'], package=pid, confirm=True, remote_name=remote,
                                              policy="force-upload")
                except Exception as e:
                    print(e)
                    all_success = False
        return all_success
    else:
        print("Upload of binary artifacts is disabled")
        return True

################################
#
#
#
################################
def build_workspace(deps, build_folder, config):
    name = config['meta_package']['name']
    version = config['meta_package']['version']
    user = config['meta_package']['user']
    channel = config['meta_package']['channel']

    workspace_filename = os.path.join(os.curdir,build_folder, "conanws.yml")     

    installFolder = os.path.join(os.curdir,"install")
    installFolder = os.path.abspath(installFolder)

    # create install folder
    # should the folder be cleared before installing? cases like renaming a pattern file
    if not os.path.exists(installFolder):
        os.mkdir(installFolder)
        #shutil.rmtree(installFolder)



    # Format of workspace config file: conanws.yml


    #editables:    
    #    ubitrack_core/1.3.0@user/dev:
    #        path: utcore
    #    ubitrack_vision/1.3.0@user/dev:
    #        path: utvision      
    #    ubitrack/1.3.0@user/dev:
    #        path: ubitrack
    #        layout: layout_gcc_ubitrack
    #layout: layout_gcc
    #workspace_generator: cmake
    #root: ubitrack/1.3.0@user/dev

    
    editables = {}

    for dep in deps:
        key =  "{0}/{1}@{2}/{3}".format(dep, version, "local", "dev") 
        edit = {"path" : dep}

        if dep.startswith("ubitrack"):
            editables[key] = edit


    key =  "{0}/{1}@{2}/{3}".format("ubitrack", version, "local", "dev") 
    edit = {"path" : "meta" , "layout" : "../workspace/layout_gcc_ubitrack"}
    editables[key] = edit

    workspace_config = {
        "editables": editables,
        "layout": "../workspace/layout_gcc",
        "workspace_generator": "cmake",
        "root": key,
  
        }

    
    yaml.dump(workspace_config, open(workspace_filename, "w"))

    conan_api, client_cache, user_io = Conan.factory()
    conan_api.create_app()

    build_parameter = ["*:workspaceBuild=True"]
    profile_name = global_config['profile_name'].split(",")

    result = conan_api.workspace_install(build_folder, options=build_parameter, install_folder=installFolder, profile_name=profile_name)

    return {}

@create_after(executed='load_config', target_regex='package_worker_.*')
def task_package_worker_gen():
    if not os.path.exists(BUILD_CONFIG_NAME):
        return

    build_config = yaml.load(open(BUILD_CONFIG_NAME))
    deps = []
    for dep_info in build_config['dependencies']:
        name = dep_info["name"]
        if name in SKIP_PACKAGES:
            continue

        # first clone the dependency
        prepare_task_name = "package_worker_prepare_%s" % name
        yield {
            'name': prepare_task_name,
            'file_dep': [BUILD_CONFIG_NAME,],
            'actions': [(prepare_package_repository, [name, dep_info["gitrepo"], dep_info["gitbranch"]])],
            'params': [{'name': 'build_folder',
                        'short': 'f',
                        'default': 'build'},
                       {'name': 'wipe',
                        'short': 'w',
                        'type': bool,
                        'default': False},
                       ],
            'getargs': {'config': ('load_config', "config"),
                        },
            'uptodate': [False,],
            'verbosity': 2,
        }

        # for local workspace build do not export or upload the code to conan as we are currently working with local direcories
        if not global_config["workspace"]:

            # then export it into the local conan cache
            export_task_name = "package_worker_export_%s" % name
            yield {
                'name': export_task_name,
                'file_dep': [BUILD_CONFIG_NAME,],
                'actions': [(export_package, [dep_info['conanuser'], dep_info.get('conanchannel', "stable")])],
                'getargs': {'name': ("package_worker_gen:%s" % prepare_task_name, "name"),
                            'package_repo_folder': ("package_worker_gen:%s" % prepare_task_name, "package_repo_folder"),
                            'package_commit_rev': ("package_worker_gen:%s" % prepare_task_name, "commit_rev"),
                            },
                'uptodate': [result_dep("package_worker_gen:%s" % prepare_task_name),],
                'verbosity': 2,
            }

            # then upload it to the conan repository
            upload_task_name = "package_worker_upload_%s" % name
            yield {
                'name': upload_task_name,
                'file_dep': [BUILD_CONFIG_NAME,],
                'actions': [(upload_package,)],
                'getargs': {'name': ("package_worker_gen:%s" % export_task_name, "name"),
                            'version': ("package_worker_gen:%s" % export_task_name, "version"),
                            'user': ("package_worker_gen:%s" % export_task_name, "user"),
                            'channel': ("package_worker_gen:%s" % export_task_name, "channel"),
                            'package_commit_rev': ("package_worker_gen:%s" % prepare_task_name, "commit_rev"),
                            'config': ('load_config', "config"),
                            },
                'uptodate': [result_dep("package_worker_gen:%s" % export_task_name),],
                'verbosity': 2,
            }

        deps.append(name)


    

    if global_config["workspace"]:
        # prepare the meta repository
        yield {
            'name': 'prepare_meta_repository',
            'actions': [(prepare_meta_repository,)],
            'params': [{'name': 'wipe',
                        'short': 'w',
                        'type': bool,
                        'default': False},
                       ],
            'getargs': {'meta_repo_folder': ('load_config', "meta_repo_folder"),
                        'config': ('load_config', "config"),
                        },
            'uptodate': [False],
            'verbosity': 2,
           }

        yield {
            'name': 'package_worker_workspace_build',
            'actions': [(build_workspace, [deps,])],
            'params': [{'name': 'build_folder',
                        'short': 'f',
                        'default': 'build'},
                       ],
            'getargs': {'config': ('load_config', "config"),
                        },
            #'uptodate': [result_dep("package_worker_gen:export_meta_package")],
            'uptodate': [False],
            'verbosity': 2,
        }
    else:
        # prepare the meta repository
        yield {
            'name': 'prepare_meta_repository',
            'actions': [(prepare_meta_repository,)],
            'params': [{'name': 'wipe',
                        'short': 'w',
                        'type': bool,
                        'default': False},
                       ],
            'getargs': {'meta_repo_folder': ('load_config', "meta_repo_folder"),
                        'config': ('load_config', "config"),
                        },
            'uptodate': [result_dep("package_worker_gen:package_worker_upload_%s" % n) for n in deps],
            'verbosity': 2,
           }

        # export the meta repository
        yield {
            'name': 'export_meta_package',
            'actions': [(export_meta_package,)],
            'getargs': {'meta_repo_folder': ('package_worker_gen:prepare_meta_repository', "meta_repo_folder"),
                        'meta_commit_rev': ('package_worker_gen:prepare_meta_repository', "commit_rev"),
                        'config': ('load_config', "config"),
                        },
            'uptodate': [result_dep('package_worker_gen:prepare_meta_repository')],
            'verbosity': 2,
           }

        # now build the release
        yield {
            'name': 'package_worker_build',
            'actions': [(build_release, [deps,])],
            'params': [{'name': 'build_folder',
                        'short': 'f',
                        'default': 'build'},
                       ],
            'getargs': {'config': ('load_config', "config"),
                        },
            'uptodate': [result_dep("package_worker_gen:export_meta_package")],
            'verbosity': 2,
        }

        # and deploy all resulting artefacts to the repository
        yield {
            'name': 'package_worker_deploy',
            'actions': [(deploy_release,)],
            'getargs': {'packages': ('package_worker_gen:package_worker_build', "packages"),
                        'config': ('load_config', "config"),
                        },
            'uptodate': [result_dep('package_worker_gen:package_worker_build'), ],
            'verbosity': 2,
        }


if __name__ == '__main__':
    import doit
    doit.run(globals())
