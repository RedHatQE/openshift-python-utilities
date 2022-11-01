#! /usr/bin/python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup


setup(
    name="openshift-python-utilities",
    license="apache-2.0",
    keywords=["Openshift"],
    packages=find_packages(),
    include_package_data=True,
    install_requires=["openshift", "colorlog", "pytest", "pytest-testconfig", "PyYAML"],
    python_requires=">=3.6",
)
