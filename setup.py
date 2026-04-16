from pathlib import Path

import setuptools


BASE_DIR = Path(__file__).resolve().parent
long_description = (BASE_DIR / "README.md").read_text(encoding="utf-8")


setuptools.setup(
    name="dsbapipy",
    version="0.0.14",
    author="nerrixDE",
    author_email="nerrixde@mailfence.com",
    description="API fuer die DSBMobile Vertretungsplan-App",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nerrixDE/DSBApi",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "beautifulsoup4",
        "pillow",
        "pytesseract",
        "requests",
    ],
)
