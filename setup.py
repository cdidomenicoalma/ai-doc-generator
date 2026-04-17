from setuptools import setup, find_packages

setup(
    name="docgen",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.30.0",
        "python-docx>=1.1.0",
        "rich>=13.0.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "docgen=docgen.main:main",
        ],
    },
    python_requires=">=3.9",
)
