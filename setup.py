from setuptools import setup, find_packages

setup(
    name="veriflow",
    version="1.0.0",
    description="Lightweight RTL verification and documentation framework for multi-project ASIC flows",
    author="Roman Lugo",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "veriflow": ["template/*.v"],
    },
    install_requires=[
        "pyyaml",
    ],
    extras_require={
        "docs": ["mkdocs>=1.6", "mkdocs-material>=9.5"],
    },
    entry_points={
        "console_scripts": [
            "veriflow=veriflow.cli:main",
        ],
    },
    python_requires=">=3.10",
)
