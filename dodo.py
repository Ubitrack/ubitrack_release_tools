#! /usr/bin/env python3

import os
import sys
import yaml
import shutil

import semver

from doit.tools import result_dep
from doit import create_after

from conans import __version__ as client_version
from conans.client.conan_api import (Conan, default_manifest_folder)
from conans.errors import ConanException
from conans.model.ref import ConanFileReference
from conans.client.tools import Git as ConanGit
from conans.client.runner import ConanRunner


CONAN_PROJECTREFERENCE_IS_OBJECT = semver.gte(client_version, '1.7.0', True)
BUILD_CONFIG_NAME = os.path.join(os.curdir, "build_config.yml")
SKIP_PACKAGES = ["cmake_installer", ]

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

    build_config = {
        "meta_repo_folder": meta_repo_folder,
        "dependencies": data['dependencies'],
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
    return {'actions': [(load_config,)],
            'params': [{'name': 'config',
                        'short': 'c',
                        'default': 'ubitrack-1.3.0.yml'},
                       {'name': 'build_folder',
                        'short': 'f',
                        'default': 'build'},
                       ],
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

def task_prepare_meta_repository():
    return {'actions': [(prepare_meta_repository,)],
            'params': [{'name': 'wipe',
                        'short': 'w',
                        'type': bool,
                        'default': False},
                       ],
            'getargs': {'meta_repo_folder': ('load_config', "meta_repo_folder"),
                        'config': ('load_config', "config"),
                        },
            'uptodate': [False,],
            'verbosity': 2,
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
    conan_api.export(meta_repo_folder, name=name, version=version, user=user, channel=channel)
    version = conan_api.inspect(meta_repo_folder, attributes=['version'])['version']
    return {
        "commit_rev": meta_commit_rev,
        "meta_repo_folder": meta_repo_folder,
        "name": name,
        "version": version,
        "user": user,
        "channel": channel,
        }


def task_export_meta_package():
    return {'actions': [(export_meta_package,)],
            'getargs': {'meta_repo_folder': ('prepare_meta_repository', "meta_repo_folder"),
                        'meta_commit_rev': ('prepare_meta_repository', "commit_rev"),
                        'config': ('load_config', "config"),
                        },
            'uptodate': [result_dep('prepare_meta_repository')],
            'verbosity': 2,
           }


################################
#
#
#
################################
# def parse_dependencies( meta_repo_folder, user, channel):
#     conan_api, client_cache, user_io = Conan.factory()
#     deps_graph, project_reference = conan_api.info(meta_repo_folder)

#     all_references = []
#     for node in sorted(deps_graph.nodes):
#         conan = node.conanfile
#         ref = node.conan_ref
#         if not ref:
#             # ref is only None iff info is being printed for a project directory, and
#             # not a passed in reference
#             if project_reference is None:
#                 continue
#             else:
#                 if CONAN_PROJECTREFERENCE_IS_OBJECT:
#                     ref = ConanFileReference.loads("%s/%s@%s/%s" % (project_reference.name,
#                                                    project_reference.version, user, channel))
#                 else:
#                     ref = ConanFileReference.loads("%s@%s/%s" % (project_reference.split('@')[0], user, channel))
#         all_references.append((str(ref), conan.url))

#     build_config = {
#         "meta_repo_folder": meta_repo_folder,
#         "dependencies": all_references,
#         "name": project_reference.name,
#         "version": project_reference.version,
#         "user": user,
#         "channel": channel,
#         }
#     yaml.dump(build_config, open(BUILD_CONFIG_NAME, "w"))
#     return True


# def task_parse_dependencies():
#     return {'actions': [(parse_dependencies,)],
#             'getargs': {'meta_repo_folder': ('export_meta_package', "meta_repo_folder"),
#                         'user': ('export_meta_package', "user"),
#                         'channel': ('export_meta_package', "channel"),
#                         },
#             'uptodate': [result_dep('export_meta_package')],
#             'targets': [BUILD_CONFIG_NAME,],
#             'verbosity': 2,
#            }


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
        print("Updating package-repository: %s - %s" % (gitrepo, gitbranch))
        out = scm.update()
        print("Updated package-repository.\n %s" % out)
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

    conan_api.export(package_repo_folder, name=name, version=version,
                     user=user, channel=channel)

    version = conan_api.inspect(package_repo_folder, attributes=['version'])['version']
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
    conan_api, client_cache, user_io = Conan.factory()
    conan_repo = {v['name']: v['conanuser'] for v in config['dependencies']}

    ref = "%s/%s@%s/%s" % (name, version, user, channel)
    remote = conan_repo[name]
    if remote is not None:
        result = conan_api.upload(ref, confirm=True, remote_name=remote, policy="force-upload")
    
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

    package_repo_folder = os.path.join(build_folder, "meta")

    build_modes = deps

    conan_api, client_cache, user_io = Conan.factory()
    result = conan_api.create(package_repo_folder, name=name, version=version,
                              user=user, channel=channel, build_modes=build_modes)

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


@create_after(executed='export_meta_package', target_regex='package_worker_.*')
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
        }

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
        }

        deps.append(name)

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
        'uptodate': [result_dep("package_worker_gen:package_worker_upload_%s" % n) for n in deps],
    }

    # and deploy all resulting artefacts to the repository
    yield {
        'name': 'package_worker_deploy',
        'actions': [(deploy_release,)],
        'getargs': {'packages': ('package_worker_gen:package_worker_build', "packages"),
                    'config': ('load_config', "config"),
                    },
        'uptodate': [result_dep('package_worker_gen:package_worker_build'), ],
    }


if __name__ == '__main__':
    import doit
    doit.run(globals())
