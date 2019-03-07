#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="linto_recorder",
    version="0.1.5",
    include_package_data=True,
    packages=find_packages(),
    entry_points = {
        'console_scripts': ['linto_recorder=recorder.recorder:main'],
    },
    install_requires=[
        'tenacity',
        'pyalsaaudio',
        'paho-mqtt'
    ],
    author="Rudy Baraglia",
    author_email="baraglia.rudy@gmail.com",
    description="linto_recorder allow to run video and audio recording",
    license="AGPL V3",
    keywords="video audio recorder",
    url="",
    project_urls={
        "github" : ""
    },
    long_description="Refer to README"

)