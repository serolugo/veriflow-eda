import re
import pathlib

from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()


def _read_version():
    text = (pathlib.Path(__file__).parent / "veriflow" / "__init__.py").read_text()
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not m:
        raise RuntimeError("Cannot find __version__ in __init__.py")
    return m.group(1)


setup(
    name="veriflow-eda",
    version=_read_version(),
    description="Pre-Silicon Multiproject ASIC Validation Framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Roman Lugo",
    license="MIT",
    license_files=["LICENCE"],
    python_requires=">=3.10",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "veriflow": [
            "template/*.v",
            "core/wrapper/templates/*.j2",
            "interfaces/*/*.v",
            "interfaces/*/*.yaml",
            "technologies/*.yaml",
        ],
    },
    install_requires=[
        "pyyaml",
        "jinja2",
        "rich",
    ],
    extras_require={
    "docs": ["mkdocs>=1.6", "mkdocs-material>=9.5"],
    "dev": ["pytest"],
    "pdks": ["volare"],
    },
    entry_points={
        "console_scripts": [
            "veriflow=veriflow.cli:main",
        ],
    },
    keywords=[
        "rtl", "verilog", "verification", "eda",
        "asic", "icarus-verilog", "yosys",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
        "Topic :: Software Development :: Embedded Systems",
    ],
    project_urls={
        "Homepage": "https://github.com/serolugo/veriflow",
        "Repository": "https://github.com/serolugo/veriflow",
        "Issues": "https://github.com/serolugo/veriflow/issues",
        "Changelog": "https://github.com/serolugo/veriflow/blob/main/CHANGELOG.md",
    },
)
