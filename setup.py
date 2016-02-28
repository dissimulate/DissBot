from setuptools import setup, find_packages

setup(
    name='DissBot',
    version='1.0',
    packages=find_packages(),
    include_package_data=False,
    install_requires=['ujson','requests'],
)
