# Always prefer setuptools over distutils
from setuptools import setup


setup(
    name='gclient',
    version='2021.5.31',
    description='gclient from google chromium depot_tools',
    url='https://github.com/mausys/gclient',
    author='The Chromium Authors',
    packages=['gclient', 'gclient.repo'],
    python_requires='>=3.8',
    install_requires=['colorama', 'schema'],
    entry_points={
    'console_scripts': [
        'gclient = gclient.gclient:cli',
    ],
},
)
