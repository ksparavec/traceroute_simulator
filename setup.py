#!/usr/bin/env -S python3 -B -u
"""
Setup script for tsim package - Traceroute Simulator
"""

from setuptools import setup, find_packages
import os

# Read the README file for long description
def read_readme():
    """Read README.md for package long description."""
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Traceroute Simulator - Network path discovery and simulation tool"

# Read requirements from requirements.txt
def read_requirements():
    """Read requirements from requirements.txt file."""
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    if os.path.exists(requirements_path):
        with open(requirements_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

# Define package metadata
setup(
    name='tsim',
    version='1.0.0',
    description='Traceroute Simulator - Network path discovery and simulation tool',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    author='Network Analysis Tool',
    author_email='',
    license='MIT',
    url='https://github.com/yourusername/traceroute_simulator',
    
    # Package structure - use tsim namespace
    packages=['tsim'] + ['tsim.' + pkg for pkg in find_packages(where='src')] + ['tsim.ansible'],
    package_dir={
        'tsim': 'src',
        'tsim.ansible': 'ansible'
    },
    
    # Include non-Python files
    package_data={
        'tsim': [
            '*.yaml', 
            '*.yml', 
            '*.json',
        ],
        'tsim.ansible': [
            '*.py',
            '*.yml',
            '*.yaml',
            '*.sh',
            '*.txt',
        ],
    },
    include_package_data=True,
    
    # Python version requirement
    python_requires='>=3.6',
    
    # Dependencies from requirements.txt
    install_requires=read_requirements(),
    
    # Optional dependencies
    extras_require={
        'dev': [
            'pytest>=6.0.0',
            'pytest-cov>=2.0.0',
            'flake8>=3.8.0',
        ],
        'ansible': [
            'ansible>=2.9.0',
        ],
    },
    
    # Entry points for command-line scripts
    entry_points={
        'console_scripts': [
            'tsimsh=tsim.shell.tsim_shell:main',
        ],
    },
    
    # Classification
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Topic :: System :: Networking',
        'Topic :: System :: Systems Administration',
    ],
    
    # Keywords
    keywords='traceroute networking simulation routing iptables namespace',
)