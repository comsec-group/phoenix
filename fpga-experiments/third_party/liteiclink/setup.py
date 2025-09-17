#!/usr/bin/env python3

from setuptools import setup
from setuptools import find_packages


setup(
    name="liteiclink",
    description="Small footprint and configurable Inter-Chip communication cores",
    author="Florent Kermarrec",
    author_email="florent@enjoy-digital.fr",
    url="http://enjoy-digital.fr",
    download_url="https://github.com/enjoy-digital/liteiclink",
    test_suite="test",
    license="BSD",
    python_requires="~=3.6",
    packages=find_packages(exclude=("test*", "sim*", "doc*", "examples*")),
    include_package_data=True,
)
