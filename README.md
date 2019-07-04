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