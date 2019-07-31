Ubitrack Release Tools
=======================

This package provides scripts for ubitrack development and release management.

Requirements:
-------------
- conan (1.16+)
- doit
- git + dev tools


Create an Ubitrack Release:
---------------------------

How to use it:
- Minimal (default) ubitrack release-build:

  $ doit
  
- custom build:

  $ cp custom_build_example.yml local_build.yml

  edit local_build.yml to match your needs

  $ doit build_spec=local_build.yml
  
- update conan repositories

  add "upload=True" to the call for doit.

Local Development of Ubitrack (Conan Workspace):
------------------------------------------------

How to use it:
- Minimal (default) ubitrack release-build:

  $ doit workspace=True
  
The local build is it configured using the same config files as for the release build

Differences are that once the repositories are checked out another call to "doit workspace=True" won't update the repositories anymore

The projects are build in the folder "build" in the different source repositories. 

Ubitrack is then installed into the folder "./install" from where you can use the local build

You have to call "doit" only once. 
Afterwards can change into the build folders to call "make install" to build and install the projet to the local install folder.

To compile and install everything call "doit workspace=True" again


